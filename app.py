import json
import os
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4

from flask import (
    Flask, Response, abort, jsonify, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, URLSafeTimedSerializer
import qrcode
from qrcode.image.svg import SvgPathImage
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'JOTOAST_DB', 'sqlite:///jotoast.db'
)
app.config['SECRET_KEY'] = 'jotoast_secret_123'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

db = SQLAlchemy(app)

QRIS_DEMO_MODE = False
QRIS_IMAGE_FILENAME = 'QRIS.jpeg'
QRIS_DEMO_SIGNER = URLSafeTimedSerializer(
    app.config['SECRET_KEY'],
    salt='qris-demo'
)

ALLOWED_IMAGE_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}

GAMBAR_PRODUK_DEFAULT = {
    'Ricebowl Ayam Geprek': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRt49-WPr4cfaQ0wmF79f9XeFZ3LsQZF8N_To74ZqDimA&s=10',
    'Ricebowl Sapi Lada Hitam': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRBpZVZp8kvcr0-mE5GjMRn6t7iSCRBNMmBSWuGkxUAvg&s=10',
    'Ricebowl Sambal Matah': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSl3kU52Ipt-pszy3YqSM3JV8Fy-ztfOZczvpR-9QuemA&s=10',
    'Tost Coklat Keju': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTrakDfR2Hphw55iVvLJbshl1TEO4dy_gMV19xoYeleCyoIAoXTqSbimhk&s=10',
    'Tost Telur Smoked Beef': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTwiekxxzXk4JAKU4PC9XDj1V1KfJlWi9S_SLX2rc3TYtQ&s=10',
    'Tost Selai Kacang': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ5Cnq299qkQCYeX7zfsdOvFpD-e0JyPir95D2S-f1HLQ&s=10',
    'Kopi Susu Gula Aren': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQwZGr8NNibHhVGX5qFF-jV4hmACCOgBE4SEKZSLK0fqA&s=10',
    'Kopi Americano': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQsqI90JZHYgc6TLGtybNB5Z5cwcBqiqZ2hdB6oMKC3KQ&s=10',
    'Es Matcha Latte': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRPonM0hn0Sp4B91LmYcjj5zKkVftTp5HmU8UpwKm-zWg&s=10',
    'Ricebowl chicken with egg': 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR3pYcbJ96o0qUdu0xNVobB5viBgFKCd8C2NwWur1hWsQ&s=10',
}


# ==========================================
# FILTER FORMAT RUPIAH
# ==========================================

@app.template_filter('rupiah')
def format_rupiah(nilai):
    return "Rp{:,.0f}".format(nilai).replace(",", ".")

@app.template_filter('waktu_pesanan')
def format_waktu_pesanan(nilai):
    if not nilai:
        return '-'
    return nilai.strftime('%d/%m/%Y %H:%M')

@app.template_filter('gambar_produk')
def gambar_produk(gambar, nama):
    if not gambar:
        return GAMBAR_PRODUK_DEFAULT.get(nama)
    if gambar.startswith(('http://', 'https://')):
        return gambar

    filename = gambar.lstrip('/')
    if filename.startswith('static/'):
        filename = filename[len('static/'):]
    return url_for('static', filename=filename)


def simpan_gambar_produk(file_gambar):
    if not file_gambar or not file_gambar.filename:
        return None

    filename = secure_filename(file_gambar.filename)
    extension = os.path.splitext(filename)[1].lower()
    if (
        extension not in ALLOWED_IMAGE_TYPES
        or file_gambar.mimetype != ALLOWED_IMAGE_TYPES[extension]
    ):
        raise ValueError('Format gambar harus JPG, PNG, GIF, atau WEBP.')

    saved_filename = f'{uuid4().hex}{extension}'
    relative_path = os.path.join('uploads', saved_filename)
    upload_directory = os.path.join(app.static_folder, 'uploads')
    os.makedirs(upload_directory, exist_ok=True)
    file_gambar.save(os.path.join(app.static_folder, relative_path))
    return relative_path.replace(os.sep, '/')


def hapus_gambar_produk_baru(relative_path):
    if relative_path:
        os.remove(os.path.join(app.static_folder, relative_path))


BUKTI_BAYAR_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


def simpan_bukti_bayar(file_bukti):
    if not file_bukti or not file_bukti.filename:
        raise ValueError('Pilih file bukti pembayaran terlebih dahulu.')

    extension = os.path.splitext(secure_filename(file_bukti.filename))[1].lower()
    if (
        extension not in BUKTI_BAYAR_TYPES
        or file_bukti.mimetype != BUKTI_BAYAR_TYPES[extension]
    ):
        raise ValueError('Bukti pembayaran harus berupa JPG, PNG, atau WEBP.')

    header = file_bukti.stream.read(12)
    file_bukti.stream.seek(0)
    gambar_valid = (
        header.startswith(b'\xff\xd8\xff')
        or header.startswith(b'\x89PNG\r\n\x1a\n')
        or (header[:4] == b'RIFF' and header[8:12] == b'WEBP')
    )
    if not gambar_valid:
        raise ValueError('File bukti pembayaran bukan gambar yang valid.')

    folder = os.path.join(app.static_folder, 'uploads', 'bukti')
    os.makedirs(folder, exist_ok=True)
    nama_file = f'{uuid4().hex}{extension}'
    file_bukti.save(os.path.join(folder, nama_file))
    return f'uploads/bukti/{nama_file}'


def hapus_file_bukti(relative_path):
    if not relative_path:
        return

    try:
        os.remove(os.path.join(app.static_folder, relative_path))
    except FileNotFoundError:
        return
    except OSError:
        app.logger.exception('Gagal menghapus bukti pembayaran %s', relative_path)


@app.errorhandler(404)
def halaman_tidak_ditemukan(error):
    return render_template('404.html'), 404
@app.errorhandler(413)
def file_terlalu_besar(error):
    flash('Ukuran file terlalu besar. Maksimal 5 MB.', 'error')
    return redirect(request.referrer or url_for('home'))


# ==========================================
# 1. MODEL DATABASE
# ==========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)


class Kategori(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(50), nullable=False)

    produk = db.relationship(
        'Produk',
        backref='kategori_rel',
        lazy=True
    )


class Produk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    harga = db.Column(db.Integer, nullable=False)
    harga_modal = db.Column(db.Integer, nullable=True)
    status_ready = db.Column(db.Boolean, default=True)
    stok = db.Column(db.Integer, default=0, nullable=False)

    gambar = db.Column(db.String(500), nullable=True)

    kategori_id = db.Column(
        db.Integer,
        db.ForeignKey('kategori.id'),
        nullable=False
    )

    varian = db.relationship(
        'Varian',
        backref='produk',
        cascade='all, delete-orphan',
        lazy=True
    )

# SPRINT 2: tabel varian produk
class Varian(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produk_id = db.Column(
        db.Integer,
        db.ForeignKey('produk.id'),
        nullable=False
    )
    nama = db.Column(db.String(50), nullable=False)
    harga_tambahan = db.Column(db.Integer, default=0, nullable=False)

class Transaksi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_pemesan = db.Column(db.String(100), nullable=True)
    metode_bayar = db.Column(db.String(20), nullable=False)
    total_harga = db.Column(db.Integer, nullable=False)
    tanggal_waktu = db.Column(db.DateTime, nullable=True, default=datetime.now)

    # Membedakan transaksi online dan transaksi kasir
    sumber = db.Column(
        db.String(20),
        nullable=False,
        default='Kasir'
    )

    # Status pengerjaan pesanan:
    # Menunggu Pembayaran -> Diproses -> Siap Diambil -> Selesai
    status = db.Column(
        db.String(30),
        nullable=False,
        default='Menunggu Pembayaran'
    )

    # SPRINT 2
    kode_pesanan = db.Column(db.String(12), nullable=True, index=True)
    tipe_pembayaran = db.Column(db.String(20), nullable=True)   # Tunai / Non Tunai
    status_pembayaran = db.Column(
        db.String(25),
        nullable=False,
        default='Belum Dibayar'     # Belum Dibayar / Menunggu Verifikasi / Lunas
    )
    uang_diterima = db.Column(db.Integer, nullable=True)
    kembalian = db.Column(db.Integer, nullable=True)
    waktu_bayar = db.Column(db.DateTime, nullable=True)
    bukti_bayar = db.Column(db.String(255), nullable=True)

class DetailTransaksi(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    transaksi_id = db.Column(
        db.Integer,
        db.ForeignKey('transaksi.id'),
        nullable=False
    )

    produk_id = db.Column(
        db.Integer,
        db.ForeignKey('produk.id'),
        nullable=False
    )

    nama_produk = db.Column(db.String(100), nullable=False)
    varian = db.Column(db.String(50), nullable=True)   # SPRINT 2
    harga = db.Column(db.Integer, nullable=False)
    harga_modal = db.Column(db.Integer, nullable=True)
    jumlah = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Integer, nullable=False)


# ==========================================
# 2. MEMBUAT DAN MEMPERBARUI DATABASE
# ==========================================

with app.app_context():
    db.create_all()

    def tambah_kolom(tabel, nama_kolom, definisi):
        """Tambah kolom ke tabel lama jika belum ada. True jika baru dibuat."""
        kolom_ada = {
            item['name'] for item in inspect(db.engine).get_columns(tabel)
        }
        if nama_kolom in kolom_ada:
            return False
        db.session.execute(text(
            f'ALTER TABLE {tabel} ADD COLUMN {nama_kolom} {definisi}'
        ))
        return True

    tambah_kolom('transaksi', 'sumber', "VARCHAR(20) NOT NULL DEFAULT 'Kasir'")
    tambah_kolom('transaksi', 'status', "VARCHAR(30) NOT NULL DEFAULT 'Menunggu Pembayaran'")
    tambah_kolom('transaksi', 'tanggal_waktu', 'DATETIME')
    tambah_kolom('produk', 'gambar', 'VARCHAR(500)')
    tambah_kolom('produk', 'harga_modal', 'INTEGER')

    # ---- SPRINT 2 ----
    tambah_kolom('transaksi', 'kode_pesanan', 'VARCHAR(12)')
    tambah_kolom('transaksi', 'tipe_pembayaran', 'VARCHAR(20)')
    tambah_kolom('transaksi', 'uang_diterima', 'INTEGER')
    tambah_kolom('transaksi', 'kembalian', 'INTEGER')
    tambah_kolom('transaksi', 'waktu_bayar', 'DATETIME')
    tambah_kolom('transaksi', 'bukti_bayar', 'VARCHAR(255)')
    kolom_baru = tambah_kolom(
        'transaksi', 'status_pembayaran',
        "VARCHAR(25) NOT NULL DEFAULT 'Belum Dibayar'"
    )
    tambah_kolom('detail_transaksi', 'varian', 'VARCHAR(50)')
    tambah_kolom('detail_transaksi', 'harga_modal', 'INTEGER')

    db.session.execute(text("""
        UPDATE detail_transaksi
        SET harga_modal = (
            SELECT produk.harga_modal
            FROM produk
            WHERE produk.id = detail_transaksi.produk_id
        )
        WHERE harga_modal IS NULL
        AND EXISTS (
            SELECT 1
            FROM produk
            WHERE produk.id = detail_transaksi.produk_id
            AND produk.harga_modal IS NOT NULL
        )
    """))

    if kolom_baru:
        # Rapikan data lama dari Sprint 1
        db.session.execute(text("""
            UPDATE transaksi
            SET status_pembayaran = 'Lunas', status = 'Selesai'
            WHERE sumber = 'Kasir'
        """))
        db.session.execute(text("""
            UPDATE transaksi SET status_pembayaran = 'Lunas'
            WHERE status = 'Selesai'
        """))
        db.session.execute(text("""
            UPDATE transaksi SET status = 'Menunggu Pembayaran'
            WHERE status = 'Menunggu'
        """))
        db.session.execute(text("""
            UPDATE transaksi
            SET tipe_pembayaran = CASE
                WHEN metode_bayar LIKE 'Non%' OR metode_bayar = 'QRIS'
                THEN 'Non Tunai' ELSE 'Tunai' END
        """))
        # Pesanan online tunai langsung diproses (dibayar saat pengambilan)
        db.session.execute(text("""
            UPDATE transaksi SET status = 'Diproses'
            WHERE sumber = 'Online'
            AND metode_bayar = 'Tunai'
            AND status = 'Menunggu Pembayaran'
        """))

    db.session.commit()


# ==========================================
# 3. LOGIN
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        user = User.query.filter_by(
            username=username,
            password=password,
            role=role
        ).first()

        if user:

            session['user_id'] = user.id
            session['role'] = user.role

            if user.role == 'owner':
                return redirect(url_for('kelola_produk'))

            elif user.role == 'kasir':
                return redirect(url_for('kasir'))

        else:
            return render_template(
                'login.html',
                error='Username atau kata sandi salah.'
            )

    return render_template('login.html')


# ==========================================
# 4. KELOLA PRODUK
# ==========================================

@app.route('/admin/produk')
def kelola_produk():

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    kategori_aktif = request.args.get('kategori', 'semua')
    kategori_list = Kategori.query.order_by(Kategori.nama).all()

    if kategori_aktif == 'semua':
        produk = Produk.query.all()
    else:
        kategori = Kategori.query.filter_by(nama=kategori_aktif).first()
        produk = (
            Produk.query.filter_by(kategori_id=kategori.id).all()
            if kategori else []
        )

    return render_template(
        'admin_produk.html',
        produk=produk,
        kategori=kategori_list,
        kategori_aktif=kategori_aktif
    )



@app.route('/admin/produk/tambah', methods=['GET', 'POST'])
def tambah_produk():

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    if request.method == 'POST':

        try:
            nama = request.form.get('nama', '').strip()
            harga = int(request.form.get('harga'))
            harga_modal_form = request.form.get('harga_modal', '').strip()
            harga_modal = int(harga_modal_form) if harga_modal_form else None
            kategori_id = int(request.form.get('kategori_id'))
            stok = int(request.form.get('stok', 0))

            if not nama:
                raise ValueError('Nama produk harus diisi.')

            if (
                harga < 0
                or stok < 0
                or (harga_modal is not None and harga_modal < 0)
            ):
                raise ValueError('Harga, modal, dan stok tidak boleh negatif!')

            gambar = simpan_gambar_produk(request.files.get('gambar'))
            produk_baru = Produk(
                nama=nama,
                harga=harga,
                harga_modal=harga_modal,
                kategori_id=kategori_id,
                stok=stok,
                status_ready=stok > 0,
                gambar=gambar
            )

            db.session.add(produk_baru)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                hapus_gambar_produk_baru(gambar)
                raise

            flash('Produk berhasil ditambahkan.', 'admin_success')

            return redirect(url_for('kelola_produk'))

        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(
                str(error) if isinstance(error, ValueError) else 'Data produk tidak valid.',
                'admin_error'
            )

    kategori_list = Kategori.query.all()

    return render_template(
        'admin_tambah_produk.html',
        kategori=kategori_list
    )




@app.route('/admin/produk/edit/<int:id>', methods=['GET', 'POST'])
def edit_produk(id):

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    produk = Produk.query.get_or_404(id)

    if request.method == 'POST':

        try:
            nama = request.form.get('nama', '').strip()
            harga = int(request.form.get('harga'))
            harga_modal_form = request.form.get('harga_modal', '').strip()
            harga_modal = int(harga_modal_form) if harga_modal_form else None
            kategori_id = int(request.form.get('kategori_id'))
            stok = int(request.form.get('stok', 0))

            if not nama:
                raise ValueError('Nama produk harus diisi.')

            if (
                harga < 0
                or stok < 0
                or (harga_modal is not None and harga_modal < 0)
            ):
                raise ValueError('Harga, modal, dan stok tidak boleh negatif!')

            gambar = simpan_gambar_produk(request.files.get('gambar'))
            produk.nama = nama
            produk.harga = harga
            produk.harga_modal = harga_modal
            produk.kategori_id = kategori_id
            produk.stok = stok
            produk.status_ready = stok > 0

            if gambar is not None:
                produk.gambar = gambar

            rincian_lama_dilengkapi = 0
            if harga_modal is not None:
                rincian_lama_dilengkapi = (
                    DetailTransaksi.query
                    .filter_by(produk_id=produk.id, harga_modal=None)
                    .update(
                        {DetailTransaksi.harga_modal: harga_modal},
                        synchronize_session=False
                    )
                )

            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                hapus_gambar_produk_baru(gambar)
                raise

            pesan = 'Produk berhasil diperbarui.'
            if rincian_lama_dilengkapi:
                pesan += (
                    f' Harga modal juga diterapkan ke '
                    f'{rincian_lama_dilengkapi} rincian transaksi lama '
                    'yang belum memiliki data modal.'
                )
            flash(pesan, 'admin_success')

            return redirect(url_for('kelola_produk'))

        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(
                str(error) if isinstance(error, ValueError) else 'Data produk tidak valid.',
                'admin_error'
            )

    kategori_list = Kategori.query.all()

    return render_template(
        'admin_edit_produk.html',
        produk=produk,
        kategori=kategori_list
    )


@app.route('/admin/produk/hapus/<int:id>')
def hapus_produk(id):

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    produk = Produk.query.get(id)

    if produk:
        db.session.delete(produk)
        db.session.commit()
        flash('Produk berhasil dihapus.', 'admin_success')

    return redirect(url_for('kelola_produk'))


# ==========================================
# 5. KELOLA KATEGORI
# ==========================================

@app.route('/admin/kategori', methods=['GET', 'POST'])
def kelola_kategori():

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    if request.method == 'POST':

        nama = request.form.get('nama', '').strip()

        if nama:
            kategori_baru = Kategori(nama=nama)

            db.session.add(kategori_baru)
            db.session.commit()
            flash('Kategori berhasil ditambahkan.', 'admin_success')

        return redirect(url_for('kelola_kategori'))

    kategori_list = Kategori.query.all()

    return render_template(
        'admin_kategori.html',
        kategori=kategori_list
    )


@app.route('/admin/kategori/hapus/<int:id>')
def hapus_kategori(id):

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    kategori = Kategori.query.get(id)

    if kategori:

        # Jangan hapus kategori jika masih memiliki produk
        if kategori.produk:
            flash(
                'Kategori tidak dapat dihapus karena masih memiliki produk.',
                'admin_error'
            )
        else:
            db.session.delete(kategori)
            db.session.commit()
            flash('Kategori berhasil dihapus.', 'admin_success')

    return redirect(url_for('kelola_kategori'))


# ==========================================
# 6. LOGOUT
# ==========================================

@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('home'))


# ==========================================
# 7. HALAMAN KASIR
# ==========================================

@app.route('/kasir')
def kasir():

    if session.get('role') != 'kasir':
        return redirect(url_for('login'))

    produk = Produk.query.all()
    kategori = Kategori.query.all()

    return render_template(
        'kasir.html',
        produk=produk,
        kategori=kategori
    )


@app.route('/riwayat-transaksi')
def riwayat_transaksi():

    role = session.get('role')
    if role not in ['owner', 'kasir']:
        return redirect(url_for('login'))

    transaksi_list = Transaksi.query.order_by(Transaksi.id.desc()).all()
    detail_list = (
        DetailTransaksi.query
        .filter(DetailTransaksi.transaksi_id.in_(
            [transaksi.id for transaksi in transaksi_list]
        ))
        .order_by(DetailTransaksi.id)
        .all()
        if transaksi_list else []
    )
    detail_per_transaksi = {}
    for detail in detail_list:
        detail_per_transaksi.setdefault(detail.transaksi_id, []).append(detail)

    transaksi_lunas_ids = {
        transaksi.id
        for transaksi in transaksi_list
        if transaksi.status_pembayaran == 'Lunas'
    }
    penjualan_per_produk = {}
    for detail in detail_list:
        if detail.transaksi_id not in transaksi_lunas_ids:
            continue

        ringkasan = penjualan_per_produk.setdefault(
            detail.produk_id,
            {'nama_produk': detail.nama_produk, 'jumlah_terjual': 0}
        )
        ringkasan['nama_produk'] = detail.nama_produk
        ringkasan['jumlah_terjual'] += detail.jumlah

    produk_terlaris = min(
        penjualan_per_produk.values(),
        key=lambda produk: (
            -produk['jumlah_terjual'],
            produk['nama_produk'].casefold()
        ),
        default=None
    )

    return render_template(
        'riwayat_transaksi.html',
        transaksi=transaksi_list,
        detail_per_transaksi=detail_per_transaksi,
        produk_terlaris=produk_terlaris,
        total_penjualan_lunas=sum(
            transaksi.total_harga
            for transaksi in transaksi_list
            if transaksi.status_pembayaran == 'Lunas'
        ),
        role=role
    )


@app.route('/admin/diagram')
def admin_diagram():
    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    transaksi_list = Transaksi.query.order_by(Transaksi.tanggal_waktu.asc()).all()
    produk_list = Produk.query.all()
    kategori_list = Kategori.query.order_by(Kategori.nama.asc()).all()

    hari_ini = datetime.now().date()
    tanggal_laporan = [
        hari_ini - timedelta(days=hari_ke)
        for hari_ke in range(6, -1, -1)
    ]
    penjualan_harian = {tanggal: 0 for tanggal in tanggal_laporan}
    for transaksi in transaksi_list:
        if (
            transaksi.status_pembayaran == 'Lunas'
            and transaksi.tanggal_waktu
            and transaksi.tanggal_waktu.date() in penjualan_harian
        ):
            penjualan_harian[transaksi.tanggal_waktu.date()] += transaksi.total_harga

    status_pembayaran = {}
    sumber_transaksi = {}
    for transaksi in transaksi_list:
        status = transaksi.status_pembayaran or 'Tidak diketahui'
        status_pembayaran[status] = status_pembayaran.get(status, 0) + 1

        sumber = transaksi.sumber or 'Tidak diketahui'
        sumber_transaksi[sumber] = sumber_transaksi.get(sumber, 0) + 1

    jumlah_produk_per_kategori = {kategori.id: 0 for kategori in kategori_list}
    nama_kategori = {kategori.id: kategori.nama for kategori in kategori_list}
    for produk in produk_list:
        jumlah_produk_per_kategori[produk.kategori_id] = (
            jumlah_produk_per_kategori.get(produk.kategori_id, 0) + 1
        )

    def siapkan_baris_diagram(data, label_nilai):
        data = list(data)
        nilai_maksimum = max((nilai for _, nilai in data), default=0)
        total_nilai = sum(nilai for _, nilai in data)
        sudut_sebelumnya = 0
        baris = []
        for indeks, (label, nilai) in enumerate(data):
            sudut_akhir = (
                100 if total_nilai and indeks == len(data) - 1
                else sudut_sebelumnya + (
                    nilai * 100 / total_nilai if total_nilai else 0
                )
            )
            baris.append({
                'label': label,
                'nilai': nilai,
                'label_nilai': label_nilai(nilai),
                'persentase': (
                    max(1, round(nilai * 100 / nilai_maksimum))
                    if nilai_maksimum and nilai > 0 else 0
                ),
                'sudut_mulai': round(sudut_sebelumnya, 4),
                'sudut_akhir': round(sudut_akhir, 4)
            })
            sudut_sebelumnya = sudut_akhir
        return baris

    return render_template(
        'admin_diagram.html',
        total_transaksi=len(transaksi_list),
        total_penjualan_lunas=sum(
            transaksi.total_harga
            for transaksi in transaksi_list
            if transaksi.status_pembayaran == 'Lunas'
        ),
        total_produk=len(produk_list),
        total_kategori=len(kategori_list),
        diagram_penjualan=siapkan_baris_diagram(
            [
                (tanggal.strftime('%d/%m'), penjualan_harian[tanggal])
                for tanggal in tanggal_laporan
            ],
            format_rupiah
        ),
        diagram_status_pembayaran=siapkan_baris_diagram(
            sorted(status_pembayaran.items(), key=lambda item: (-item[1], item[0])),
            lambda nilai: f'{nilai} transaksi'
        ),
        total_diagram_status=sum(status_pembayaran.values()),
        diagram_produk_kategori=siapkan_baris_diagram(
            sorted(
                [
                    (nama_kategori.get(kategori_id, 'Kategori tidak diketahui'), jumlah)
                    for kategori_id, jumlah in jumlah_produk_per_kategori.items()
                ],
                key=lambda item: (item[0].casefold(), item[0])
            ),
            lambda nilai: f'{nilai} produk'
        ),
        diagram_sumber_transaksi=siapkan_baris_diagram(
            sorted(sumber_transaksi.items(), key=lambda item: (-item[1], item[0])),
            lambda nilai: f'{nilai} transaksi'
        ),
        total_diagram_sumber=sum(sumber_transaksi.values())
    )


def parse_bulan_laporan():
    nilai = request.args.get('bulan')
    if not nilai:
        sekarang = datetime.now()
        return datetime(sekarang.year, sekarang.month, 1)

    try:
        bulan = datetime.strptime(nilai, '%Y-%m')
    except ValueError:
        abort(400, description='Format bulan harus YYYY-MM.')

    if bulan.strftime('%Y-%m') != nilai:
        abort(400, description='Format bulan harus YYYY-MM.')
    return bulan.replace(day=1)


def bulan_berikutnya(bulan):
    if bulan.month == 12:
        return datetime(bulan.year + 1, 1, 1)
    return datetime(bulan.year, bulan.month + 1, 1)


def label_bulan(bulan):
    nama_bulan = (
        'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
        'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
    )
    return f'{nama_bulan[bulan.month - 1]} {bulan.year}'


def ambil_data_transaksi_lunas():
    transaksi_lunas = Transaksi.query.filter_by(
        status_pembayaran='Lunas'
    ).all()
    transaksi_ids = [transaksi.id for transaksi in transaksi_lunas]
    detail_list = (
        DetailTransaksi.query
        .filter(DetailTransaksi.transaksi_id.in_(transaksi_ids))
        .order_by(DetailTransaksi.id)
        .all()
        if transaksi_ids else []
    )
    detail_per_transaksi = {}
    for detail in detail_list:
        detail_per_transaksi.setdefault(detail.transaksi_id, []).append(detail)
    return transaksi_lunas, detail_per_transaksi


def hitung_laporan_keuangan(
    mulai, selesai, transaksi_lunas, detail_per_transaksi
):
    transaksi_per_hari = {}
    transaksi_terpilih = []

    for transaksi in transaksi_lunas:
        waktu_laporan = transaksi.waktu_bayar or transaksi.tanggal_waktu
        if mulai is not None and selesai is not None:
            if not waktu_laporan or not (mulai <= waktu_laporan < selesai):
                continue
        tanggal = waktu_laporan.date() if waktu_laporan else None
        transaksi_terpilih.append((transaksi, tanggal))
        if tanggal is None:
            continue

        ringkasan_harian = transaksi_per_hari.setdefault(
            tanggal,
            {
                'jumlah_transaksi': 0,
                'pendapatan': 0,
                'hpp_diketahui': 0,
                'laba_tercatat': 0,
                'pendapatan_bermodal': 0,
                'transaksi_tidak_lengkap': 0
            }
        )
        ringkasan_harian['jumlah_transaksi'] += 1
        ringkasan_harian['pendapatan'] += transaksi.total_harga

    laporan = {
        'jumlah_transaksi': len(transaksi_terpilih),
        'pendapatan': sum(
            transaksi.total_harga for transaksi, _ in transaksi_terpilih
        ),
        'hpp_diketahui': 0,
        'laba_tercatat': 0,
        'pendapatan_bermodal': 0,
        'jumlah_item': 0,
        'jumlah_item_modal_diketahui': 0,
        'transaksi_tidak_lengkap': 0,
        'transaksi_per_hari': transaksi_per_hari
    }

    for transaksi, tanggal in transaksi_terpilih:
        rincian = detail_per_transaksi.get(transaksi.id, [])
        tidak_lengkap = not rincian
        for detail in rincian:
            jumlah = detail.jumlah
            laporan['jumlah_item'] += jumlah
            if detail.harga_modal is None:
                tidak_lengkap = True
                continue

            hpp = detail.harga_modal * jumlah
            laba = detail.subtotal - hpp
            laporan['hpp_diketahui'] += hpp
            laporan['laba_tercatat'] += laba
            laporan['pendapatan_bermodal'] += detail.subtotal
            laporan['jumlah_item_modal_diketahui'] += jumlah

            if tanggal is not None:
                ringkasan_harian = laporan['transaksi_per_hari'][tanggal]
                ringkasan_harian['hpp_diketahui'] += hpp
                ringkasan_harian['laba_tercatat'] += laba
                ringkasan_harian['pendapatan_bermodal'] += detail.subtotal

        if tidak_lengkap:
            laporan['transaksi_tidak_lengkap'] += 1
            if tanggal is not None:
                laporan['transaksi_per_hari'][tanggal]['transaksi_tidak_lengkap'] += 1

    return laporan


def bulan_terakhir(bulan_terpilih, jumlah):
    awal = bulan_terpilih.year * 12 + bulan_terpilih.month - 1
    bulan_list = []
    for offset in range(jumlah - 1, -1, -1):
        tahun_bulan = awal - offset
        tahun, bulan_nol = divmod(tahun_bulan, 12)
        bulan_list.append(datetime(tahun, bulan_nol + 1, 1))
    return bulan_list


@app.route('/admin/pendapatan')
def admin_pendapatan():
    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    transaksi_lunas, detail_per_transaksi = ambil_data_transaksi_lunas()
    periode = request.args.get('mode', 'bulan')
    if periode not in ('bulan', 'keseluruhan'):
        abort(400, description='Periode laporan tidak valid.')

    bulan = parse_bulan_laporan() if periode == 'bulan' else datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    mulai = bulan if periode == 'bulan' else None
    selesai = bulan_berikutnya(bulan) if periode == 'bulan' else None
    laporan = hitung_laporan_keuangan(
        mulai, selesai,
        transaksi_lunas, detail_per_transaksi
    )
    return render_template(
        'admin_pendapatan.html',
        bulan=bulan.strftime('%Y-%m'),
        nama_bulan=label_bulan(bulan) if periode == 'bulan' else 'Semua Periode',
        laporan=laporan,
        periode=periode
    )


@app.route('/admin/laporan-penjualan')
def admin_laporan_penjualan():
    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    transaksi_lunas, detail_per_transaksi = ambil_data_transaksi_lunas()
    bulan = parse_bulan_laporan()
    selesai = bulan_berikutnya(bulan)
    laporan = hitung_laporan_keuangan(
        bulan, selesai, transaksi_lunas, detail_per_transaksi
    )
    data_harian = []
    tanggal = bulan.date()
    while tanggal < selesai.date():
        ringkasan = laporan['transaksi_per_hari'].get(tanggal, {})
        data_harian.append({
            'tanggal': tanggal,
            'jumlah_transaksi': ringkasan.get('jumlah_transaksi', 0),
            'pendapatan': ringkasan.get('pendapatan', 0),
            'laba_tercatat': ringkasan.get('laba_tercatat', 0),
            'transaksi_tidak_lengkap': ringkasan.get(
                'transaksi_tidak_lengkap', 0
            )
        })
        tanggal += timedelta(days=1)

    riwayat_bulanan = []
    for bulan_riwayat in bulan_terakhir(bulan, 12):
        ringkasan_bulan = hitung_laporan_keuangan(
            bulan_riwayat,
            bulan_berikutnya(bulan_riwayat),
            transaksi_lunas,
            detail_per_transaksi
        )
        riwayat_bulanan.append({
            'bulan': label_bulan(bulan_riwayat),
            'jumlah_transaksi': ringkasan_bulan['jumlah_transaksi'],
            'pendapatan': ringkasan_bulan['pendapatan']
        })

    return render_template(
        'admin_laporan_penjualan.html',
        bulan=bulan.strftime('%Y-%m'),
        nama_bulan=label_bulan(bulan),
        laporan=laporan,
        data_harian=data_harian,
        riwayat_bulanan=riwayat_bulanan
    )


# ==========================================
# 8. PROSES TRANSAKSI LANGSUNG DI KASIR
# ==========================================

@app.route('/kasir/proses_transaksi', methods=['POST'])
def proses_transaksi():

    if session.get('role') != 'kasir':
        return redirect(url_for('login'))

    try:

        # Ambil data keranjang dari kasir.html
        items_json = request.form.get('items_json', '')
        metode_bayar = request.form.get('metode_bayar', '')
        uang_diterima = request.form.get('uang_diterima', '0')

        if metode_bayar not in ['Tunai', 'Non tunai']:
            raise ValueError('Metode pembayaran tidak valid.')

        items = json.loads(items_json)

        if not isinstance(items, list) or not items:
            raise ValueError('Keranjang masih kosong.')

        # Gabungkan produk yang sama jika dikirim lebih dari sekali
        jumlah_produk = {}

        for item in items:

            produk_id = int(item.get('id', 0))
            jumlah = int(item.get('jumlah', 0))

            if produk_id <= 0 or jumlah <= 0:
                raise ValueError('Data produk tidak valid.')

            jumlah_produk[produk_id] = (
                jumlah_produk.get(produk_id, 0) + jumlah
            )

        total_harga = 0
        daftar_produk = []

        # Periksa stok dan hitung harga dari database
        for produk_id, jumlah in jumlah_produk.items():

            produk = db.session.get(Produk, produk_id)

            if not produk:
                raise ValueError('Produk tidak ditemukan.')

            if produk.stok < jumlah:
                raise ValueError(
                    f'Stok {produk.nama} tidak mencukupi.'
                )

            if not produk.status_ready:
                raise ValueError(
                    f'{produk.nama} sedang tidak tersedia.'
                )

            subtotal = produk.harga * jumlah
            total_harga += subtotal

            daftar_produk.append({
                'produk': produk,
                'jumlah': jumlah,
                'subtotal': subtotal
            })

        # Periksa pembayaran tunai
        if metode_bayar == 'Tunai':

            uang = int(uang_diterima)

            if uang < total_harga:
                raise ValueError('Uang pembayaran masih kurang.')

        else:
            uang = total_harga

        # Simpan transaksi utama
        # BARU: simpan tipe pembayaran, uang diterima, dan kembalian
        transaksi_baru = Transaksi(
            nama_pemesan='Pelanggan Outlet',
            metode_bayar=metode_bayar,
            tipe_pembayaran=(
                'Tunai' if metode_bayar == 'Tunai' else 'Non Tunai'
            ),
            status_pembayaran='Lunas',
            uang_diterima=uang,
            kembalian=uang - total_harga,
            total_harga=total_harga,
            tanggal_waktu=datetime.now(),
            waktu_bayar=datetime.now(),
            sumber='Kasir',
            status='Selesai'
        )

        db.session.add(transaksi_baru)
        db.session.flush()

        # Simpan detail dan kurangi stok
        for item in daftar_produk:

            produk = item['produk']

            detail = DetailTransaksi(
                transaksi_id=transaksi_baru.id,
                produk_id=produk.id,
                nama_produk=produk.nama,
                harga=produk.harga,
                harga_modal=produk.harga_modal,
                jumlah=item['jumlah'],
                subtotal=item['subtotal']
            )

            db.session.add(detail)

            produk.stok -= item['jumlah']
            produk.status_ready = produk.stok > 0

        db.session.commit()

        kembalian = uang - total_harga

        flash(
            f'Transaksi berhasil! Total: {format_rupiah(total_harga)}. '
            f'Kembalian: {format_rupiah(kembalian)}.',
            'kasir_success'
        )

        return redirect(url_for('kasir'))

    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:

        db.session.rollback()
        flash(str(e), 'kasir_error')

        return redirect(url_for('kasir'))

    except Exception:

        db.session.rollback()
        app.logger.exception('Gagal menyimpan transaksi kasir')

        flash(
            'Terjadi kesalahan saat menyimpan transaksi.',
            'kasir_error'
        )

        return redirect(url_for('kasir'))

# ==========================================
# 9. HALAMAN PESANAN ONLINE (SPRINT 3: DAFTAR + DETAIL)
# ==========================================

DAFTAR_STATUS_PESANAN = [
    'Menunggu Pembayaran', 'Diproses', 'Siap Diambil', 'Selesai'
]


def detail_per_pesanan(daftar_id):
    """Kelompokkan rincian menu per transaksi dalam satu query."""
    hasil = {}
    if not daftar_id:
        return hasil
    rincian = (
        DetailTransaksi.query
        .filter(DetailTransaksi.transaksi_id.in_(daftar_id))
        .order_by(DetailTransaksi.id)
        .all()
    )
    for item in rincian:
        hasil.setdefault(item.transaksi_id, []).append(item)
    return hasil


@app.route('/kasir/pesanan')
def pesanan_online():

    if session.get('role') != 'kasir':
        return redirect(url_for('login'))

    filter_status = request.args.get('status', '').strip()
    if filter_status not in DAFTAR_STATUS_PESANAN:
        filter_status = ''
    kata_kunci = request.args.get('q', '').strip()[:100]

    semua = (
        Transaksi.query
        .filter_by(sumber='Online')
        .order_by(Transaksi.id.desc())
        .all()
    )

    jumlah_status = {status: 0 for status in DAFTAR_STATUS_PESANAN}
    for trx in semua:
        if trx.status in jumlah_status:
            jumlah_status[trx.status] += 1

    kata = kata_kunci.lower()
    terfilter = [
        trx for trx in semua
        if (not filter_status or trx.status == filter_status)
        and (
            not kata
            or kata in (trx.nama_pemesan or '').lower()
            or kata in (trx.kode_pesanan or '').lower()
        )
    ]
    # Pesanan yang masih berjalan tampil lebih dulu, yang selesai di bawah
    terfilter.sort(key=lambda trx: trx.status == 'Selesai')

    rincian = detail_per_pesanan([trx.id for trx in terfilter])

    daftar_pesanan = [
        {
            'transaksi': trx,
            'detail': rincian.get(trx.id, []),
            'jumlah_item': sum(
                item.jumlah for item in rincian.get(trx.id, [])
            ),
        }
        for trx in terfilter
    ]

    return render_template(
        'pesanan_online.html',
        daftar_pesanan=daftar_pesanan,
        daftar_status=DAFTAR_STATUS_PESANAN,
        jumlah_status=jumlah_status,
        jumlah_semua=len(semua),
        filter_status=filter_status,
        kata_kunci=kata_kunci
    )


@app.route('/kasir/pesanan/<int:id>')
def detail_pesanan(id):

    if session.get('role') != 'kasir':
        return redirect(url_for('login'))

    transaksi = db.session.get(Transaksi, id)

    if not transaksi or transaksi.sumber != 'Online':
        flash('Pesanan tidak ditemukan.', 'kasir_error')
        return redirect(url_for('pesanan_online'))

    detail = detail_per_pesanan([transaksi.id]).get(transaksi.id, [])

    return render_template(
        'detail_pesanan.html',
        transaksi=transaksi,
        detail=detail,
        langkah=DAFTAR_STATUS_PESANAN,
        indeks_status=(
            DAFTAR_STATUS_PESANAN.index(transaksi.status)
            if transaksi.status in DAFTAR_STATUS_PESANAN else 0
        )
    )


# ==========================================
# 10. UBAH STATUS, KONFIRMASI TUNAI, DAN SELESAIKAN PESANAN ONLINE
# ==========================================

@app.route(
    '/kasir/pesanan/<int:id>/<aksi>',
    methods=['POST']
)
def ubah_status_pesanan(id, aksi):

    if session.get('role') != 'kasir':
        return redirect(url_for('login'))

    transaksi = db.session.get(Transaksi, id)

    if not transaksi or transaksi.sumber != 'Online':

        flash('Pesanan tidak ditemukan.', 'kasir_error')

        return redirect(url_for('pesanan_online'))

    # Dari halaman detail, kembali ke detail; selain itu ke daftar
    if request.form.get('kembali') == 'detail':
        tujuan = url_for('detail_pesanan', id=transaksi.id)
    else:
        tujuan = url_for('pesanan_online')

    # QRIS: Menunggu Pembayaran -> Diproses setelah pembayaran dikonfirmasi.
    if (
        aksi == 'bayar'
        and transaksi.status == 'Menunggu Pembayaran'
        and transaksi.metode_bayar == 'QRIS'
    ):

        if not transaksi.bukti_bayar:
            flash(
                'Pelanggan belum mengirim bukti pembayaran QRIS.',
                'kasir_error'
            )
            return redirect(tujuan)

        transaksi.uang_diterima = transaksi.total_harga
        transaksi.kembalian = 0
        transaksi.status_pembayaran = 'Lunas'
        transaksi.waktu_bayar = datetime.now()
        transaksi.status = 'Diproses'
        flash('Pembayaran QRIS terkonfirmasi.', 'kasir_success')

    # SPRINT 3: konfirmasi pembayaran tunai pesanan online.
    # Kasir menerima uang dari pelanggan, mengisi nominal, lalu mengonfirmasi.
    # Status pesanan tidak diubah di sini, hanya data pembayarannya.
    elif aksi == 'konfirmasi_tunai':

        if transaksi.metode_bayar != 'Tunai':
            flash(
                'Konfirmasi tunai hanya untuk pesanan dengan metode Tunai.',
                'kasir_error'
            )
            return redirect(tujuan)

        if transaksi.status_pembayaran == 'Lunas':
            flash('Pembayaran pesanan ini sudah dikonfirmasi.', 'kasir_error')
            return redirect(tujuan)

        if transaksi.status == 'Selesai':
            flash('Pesanan sudah selesai.', 'kasir_error')
            return redirect(tujuan)

        try:
            uang = int(request.form.get('uang_diterima', '').strip())
        except ValueError:
            flash('Nominal uang diterima harus berupa angka.', 'kasir_error')
            return redirect(tujuan)

        if uang < transaksi.total_harga:
            flash(
                'Uang yang diterima masih kurang '
                f'{format_rupiah(transaksi.total_harga - max(uang, 0))}.',
                'kasir_error'
            )
            return redirect(tujuan)

        transaksi.uang_diterima = uang
        transaksi.kembalian = uang - transaksi.total_harga
        transaksi.status_pembayaran = 'Lunas'
        transaksi.waktu_bayar = datetime.now()

        # Pesanan tunai versi lama masih "Menunggu Pembayaran":
        # setelah dibayar langsung masuk antrean diproses.
        if transaksi.status == 'Menunggu Pembayaran':
            transaksi.status = 'Diproses'

        flash(
            'Pembayaran tunai dikonfirmasi. '
            f'Kembalian: {format_rupiah(transaksi.kembalian)}.',
            'kasir_success'
        )

    # Diproses -> Siap Diambil
    elif aksi == 'siap' and transaksi.status == 'Diproses':

        transaksi.status = 'Siap Diambil'
        flash('Pesanan siap diambil pelanggan.', 'kasir_success')

    # Siap Diambil -> Selesai
    # Tunai: pembayaran diterima saat pelanggan mengambil pesanan.
    elif aksi == 'selesai' and transaksi.status == 'Siap Diambil':

        if transaksi.status_pembayaran != 'Lunas':

            try:
                uang = int(request.form.get('uang_diterima', ''))
            except ValueError:
                uang = -1

            if uang < transaksi.total_harga:
                flash('Uang yang diterima masih kurang.', 'kasir_error')
                return redirect(tujuan)

            transaksi.uang_diterima = uang
            transaksi.kembalian = uang - transaksi.total_harga
            transaksi.status_pembayaran = 'Lunas'
            transaksi.waktu_bayar = datetime.now()
            pesan = (
                'Pembayaran tunai diterima. '
                f'Kembalian: {format_rupiah(transaksi.kembalian)}. '
                'Pesanan selesai.'
            )

        else:
            pesan = 'Pesanan berhasil diselesaikan.'

        transaksi.status = 'Selesai'
        flash(pesan, 'kasir_success')

    else:

        flash('Perubahan status tidak valid.', 'kasir_error')

        return redirect(tujuan)

    db.session.commit()

    return redirect(tujuan)

# ==========================================
# 11. HOME DAN MENU ONLINE PELANGGAN (SPRINT 2)
# ==========================================

STATUS_URUTAN = ['Menunggu Pembayaran', 'Diproses', 'Siap Diambil', 'Selesai']

def kode_pesanan_aktif():
    """Kode pesanan terakhir customer, hanya jika pesanannya belum selesai."""
    kode = session.get('kode_terakhir')

    if not kode:
        return None

    transaksi = cari_pesanan_online(kode)

    if not transaksi or transaksi.status == 'Selesai':
        session.pop('kode_terakhir', None)
        return None

    return kode

@app.route('/')
def home():

    produk_unggulan = (
        Produk.query
        .filter_by(status_ready=True)
        .order_by(Produk.id)
        .limit(4)
        .all()
    )

    return render_template(
        'home.html',
        produk_unggulan=produk_unggulan,
        jumlah_keranjang=sum(session.get('cart', {}).values()),
        kode_terakhir=kode_pesanan_aktif()
    )


# Pilihan urutan daftar menu (SPRINT 2: berdasarkan harga)
URUTAN_MENU = {
    'termurah': (Produk.harga.asc(), Produk.nama.asc()),
    'termahal': (Produk.harga.desc(), Produk.nama.asc()),
    'nama': (Produk.nama.asc(),),
}


@app.route('/menu')
def menu_online():

    kategori_aktif = request.args.get('kategori', 'semua')
    urut_aktif = request.args.get('urut', 'default')
    if urut_aktif not in URUTAN_MENU:
        urut_aktif = 'default'

    urutan = URUTAN_MENU.get(urut_aktif, (Produk.kategori_id, Produk.nama))
    kategori_list = Kategori.query.order_by(Kategori.nama).all()

    if kategori_aktif == 'semua':

        produk = Produk.query.order_by(*urutan).all()

    else:

        kategori = Kategori.query.filter_by(
            nama=kategori_aktif
        ).first()

        produk = (
            Produk.query
            .filter_by(kategori_id=kategori.id)
            .order_by(*urutan)
            .all()
            if kategori else []
        )

    cart = session.get('cart', {})
    jumlah_keranjang = sum(cart.values())
    _, total_keranjang = baca_keranjang()

    return render_template(
        'menu_online.html',
        produk=produk,
        kategori=kategori_list,
        kategori_aktif=kategori_aktif,
        urut_aktif=urut_aktif,
        cart=cart,
        jumlah_keranjang=jumlah_keranjang,
        total_keranjang=total_keranjang
    )


# ==========================================
# 12. KERANJANG BELANJA (SPRINT 2: MENU + VARIAN + JUMLAH)
# ==========================================
# Struktur session['cart'] -> { "<produk_id>-<varian_id>": jumlah }
# varian_id = 0 jika produk tidak punya varian.

def kunci_keranjang(produk_id, varian_id=0):
    return f'{int(produk_id)}-{int(varian_id)}'


def pecah_kunci(kunci):
    bagian = str(kunci).split('-')
    produk_id = int(bagian[0])
    varian_id = int(bagian[1]) if len(bagian) > 1 else 0
    return produk_id, varian_id


def jumlah_produk_di_keranjang(cart, produk_id):
    """Total satu produk di keranjang dari semua variannya."""
    total = 0
    for kunci, jumlah in cart.items():
        try:
            if pecah_kunci(kunci)[0] == produk_id:
                total += int(jumlah)
        except (ValueError, TypeError):
            continue
    return total


def baca_keranjang():
    """Ubah isi session cart menjadi daftar item lengkap + total harga."""
    cart = session.get('cart', {})
    items = []
    total = 0

    for kunci, jumlah in cart.items():
        try:
            produk_id, varian_id = pecah_kunci(kunci)
            jumlah = int(jumlah)
        except (ValueError, TypeError):
            continue

        produk = db.session.get(Produk, produk_id)
        if not produk or jumlah <= 0:
            continue

        varian = db.session.get(Varian, varian_id) if varian_id else None
        if varian and varian.produk_id != produk.id:
            varian = None

        harga_satuan = produk.harga + (varian.harga_tambahan if varian else 0)
        subtotal = harga_satuan * jumlah
        total += subtotal

        items.append({
            'kunci': kunci,
            'produk': produk,
            'varian': varian,
            'jumlah': jumlah,
            'harga_satuan': harga_satuan,
            'subtotal': subtotal
        })

    return items, total


@app.route('/keranjang/tambah/<int:produk_id>', methods=['POST'])
def tambah_keranjang(produk_id):

    produk = Produk.query.get_or_404(produk_id)
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    cart = session.get('cart', {})

    def jawab_gagal(pesan, kode_http):
        if is_ajax_request:
            return jsonify(
                success=False,
                message=pesan,
                jumlah_keranjang=sum(cart.values())
            ), kode_http

        flash(pesan, 'error')
        return redirect(request.referrer or url_for('menu_online'))

    # Jumlah yang ingin ditambahkan (default 1, maksimal 50)
    try:
        jumlah_tambah = int(request.form.get('jumlah', 1))
    except ValueError:
        jumlah_tambah = 0

    if jumlah_tambah < 1 or jumlah_tambah > 50:
        return jawab_gagal('Jumlah pesanan tidak valid.', 400)

    # Validasi varian
    try:
        varian_id = int(request.form.get('varian_id', 0) or 0)
    except ValueError:
        varian_id = 0

    if produk.varian:
        varian = next((v for v in produk.varian if v.id == varian_id), None)
        if not varian:
            return jawab_gagal('Silakan pilih varian terlebih dahulu.', 400)
    else:
        varian, varian_id = None, 0

    # Validasi stok (semua varian produk yang sama berbagi stok)
    sudah_di_keranjang = jumlah_produk_di_keranjang(cart, produk.id)

    if not produk.status_ready or produk.stok < sudah_di_keranjang + jumlah_tambah:
        return jawab_gagal('Stok produk tidak mencukupi!', 409)

    kunci = kunci_keranjang(produk.id, varian_id)
    cart[kunci] = int(cart.get(kunci, 0)) + jumlah_tambah

    session['cart'] = cart
    session.modified = True

    nama_lengkap = produk.nama + (f' ({varian.nama})' if varian else '')
    pesan = f'{jumlah_tambah} × {nama_lengkap} ditambahkan ke keranjang.'

    if is_ajax_request:
        _, total_keranjang = baca_keranjang()
        return jsonify(
            success=True,
            message=pesan,
            jumlah_keranjang=sum(cart.values()),
            total_keranjang=total_keranjang
        )

    flash(pesan, 'sukses')
    return redirect(request.referrer or url_for('menu_online'))


@app.route('/keranjang/kurang/<string:kunci>', methods=['POST'])
def kurang_keranjang(kunci):

    cart = session.get('cart', {})

    if kunci in cart:

        cart[kunci] -= 1

        if cart[kunci] <= 0:
            del cart[kunci]

    session['cart'] = cart
    session.modified = True

    return redirect(url_for('checkout'))


@app.route('/keranjang/hapus/<string:kunci>', methods=['POST'])
def hapus_keranjang(kunci):

    cart = session.get('cart', {})
    cart.pop(kunci, None)

    session['cart'] = cart
    session.modified = True

    return redirect(url_for('checkout'))


# ==========================================
# 13. CHECKOUT ONLINE PELANGGAN (SPRINT 2)
# ==========================================

METODE_ONLINE = {
    'Tunai': 'Tunai',     # dibayar tunai saat mengambil pesanan di outlet
    'QRIS': 'Non Tunai',  # bayar lewat QRIS
}


def buat_kode_pesanan():
    while True:
        kode = 'JT-' + secrets.token_hex(3).upper()
        if not Transaksi.query.filter_by(kode_pesanan=kode).first():
            return kode


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():

    items, total = baca_keranjang()

    # Periksa keranjang kosong
    if not items:

        if request.method == 'POST':
            flash('Keranjang masih kosong.', 'error')

        return render_template(
            'checkout.html',
            items=[],
            total=0
        )

    # Proses checkout
    if request.method == 'POST':

        nama_pemesan = request.form.get('nama_pemesan', '').strip()
        metode_bayar = request.form.get('metode_bayar', '').strip()

        if not nama_pemesan:
            flash('Nama pemesan harus diisi.', 'error')
            return redirect(url_for('checkout'))

        if len(nama_pemesan) > 100:
            flash('Nama pemesan terlalu panjang.', 'error')
            return redirect(url_for('checkout'))

        if metode_bayar not in METODE_ONLINE:
            flash('Silakan pilih metode pembayaran.', 'error')
            return redirect(url_for('checkout'))

        try:

            # Periksa stok terbaru (semua varian satu produk berbagi stok)
            jumlah_per_produk = {}
            for item in items:
                produk = item['produk']
                jumlah_per_produk[produk.id] = (
                    jumlah_per_produk.get(produk.id, 0) + item['jumlah']
                )

            for item in items:

                produk = item['produk']

                if not produk.status_ready:
                    raise ValueError(
                        f'{produk.nama} sedang tidak tersedia.'
                    )

                if produk.stok < jumlah_per_produk[produk.id]:
                    raise ValueError(
                        f'Stok {produk.nama} tidak mencukupi.'
                    )

            kode = buat_kode_pesanan()

            # BARU: Tunai langsung diproses (dibayar saat pengambilan di outlet).
            # QRIS menunggu pembayaran; mode demo melunasi saat QR dibuka.
            status_awal = (
                'Diproses' if metode_bayar == 'Tunai' else 'Menunggu Pembayaran'
            )

            # Simpan transaksi online
            transaksi_baru = Transaksi(
                nama_pemesan=nama_pemesan,
                metode_bayar=metode_bayar,
                tipe_pembayaran=METODE_ONLINE[metode_bayar],
                status_pembayaran='Belum Dibayar',
                total_harga=total,
                tanggal_waktu=datetime.now(),
                sumber='Online',
                status=status_awal,          # BARU (sebelumnya 'Menunggu Pembayaran')
                kode_pesanan=kode
            )

            db.session.add(transaksi_baru)
            db.session.flush()

            # Simpan rincian pesanan dan kurangi stok
            for item in items:

                produk = item['produk']
                varian = item['varian']

                db.session.add(DetailTransaksi(
                    transaksi_id=transaksi_baru.id,
                    produk_id=produk.id,
                    nama_produk=produk.nama,
                    varian=varian.nama if varian else None,
                    harga=item['harga_satuan'],
                    harga_modal=produk.harga_modal,
                    jumlah=item['jumlah'],
                    subtotal=item['subtotal']
                ))

            for produk_id, jumlah in jumlah_per_produk.items():
                produk = db.session.get(Produk, produk_id)
                produk.stok -= jumlah
                produk.status_ready = produk.stok > 0

            db.session.commit()

            # Kosongkan keranjang, simpan kode pesanan terakhir
            session.pop('cart', None)
            session['kode_terakhir'] = kode

            flash('Pesanan berhasil dibuat!', 'sukses')

            if metode_bayar == 'QRIS':
                return redirect(url_for('bayar_qris', kode=kode))

            return redirect(url_for('status_pesanan', kode=kode))

        except ValueError as e:

            db.session.rollback()
            flash(str(e), 'error')
            return redirect(url_for('checkout'))

        except Exception:

            db.session.rollback()
            app.logger.exception('Gagal menyimpan checkout online')
            flash('Terjadi kesalahan saat menyimpan pesanan.', 'error')
            return redirect(url_for('checkout'))

    return render_template(
        'checkout.html',
        items=items,
        total=total
    )

# ==========================================
# 13b. CEK STATUS PESANAN (SPRINT 2)
# ==========================================

def cari_pesanan_online(kode):
    return Transaksi.query.filter_by(
        kode_pesanan=(kode or '').strip().upper(),
        sumber='Online'
    ).first()


@app.route('/cek-status', methods=['GET', 'POST'])
def cek_status():

    kode = (request.values.get('kode') or '').strip().upper()

    if kode:
        if cari_pesanan_online(kode):
            return redirect(url_for('status_pesanan', kode=kode))

        flash('Kode pesanan tidak ditemukan. Periksa kembali kodenya.', 'error')

    return render_template(
        'cek_status.html',
        kode_terakhir=kode_pesanan_aktif()
    )


@app.route('/pesanan/<kode>')
def status_pesanan(kode):

    transaksi = cari_pesanan_online(kode)

    if not transaksi:
        flash('Kode pesanan tidak ditemukan.', 'error')
        return redirect(url_for('cek_status'))

    detail = DetailTransaksi.query.filter_by(
        transaksi_id=transaksi.id
    ).order_by(DetailTransaksi.id).all()

    # Tunai langsung diproses (bayar saat ambil), jadi tanpa tahap
    # "Menunggu Pembayaran". QRIS memakai keempat tahap.
    langkah = (
        STATUS_URUTAN[1:] if transaksi.metode_bayar == 'Tunai'
        else STATUS_URUTAN
    )

    return render_template(
        'status_pesanan.html',
        transaksi=transaksi,
        detail=detail,
        langkah=langkah,
        indeks_status=(
            langkah.index(transaksi.status)
            if transaksi.status in langkah else 0
        )
    )


@app.route('/pesanan/<kode>/status.json')
def status_pesanan_json(kode):

    transaksi = cari_pesanan_online(kode)

    if not transaksi:
        return jsonify(error='Pesanan tidak ditemukan'), 404

    return jsonify(
        status=transaksi.status,
        status_pembayaran=transaksi.status_pembayaran
    )


# ==========================================
# 13c. PEMBAYARAN QRIS (SPRINT 2)
# ==========================================
# QR demo membuka URL bertanda tangan dan menyelesaikan pembayaran simulasi.

@app.route('/pesanan/<kode>/bayar', methods=['GET', 'POST'])
def bayar_qris(kode):

    transaksi = cari_pesanan_online(kode)

    if not transaksi:
        flash('Kode pesanan tidak ditemukan.', 'error')
        return redirect(url_for('cek_status'))

    if transaksi.metode_bayar != 'QRIS' or transaksi.status_pembayaran == 'Lunas':
        return redirect(url_for('status_pesanan', kode=transaksi.kode_pesanan))

    if request.method == 'POST':
        try:
            bukti_baru = simpan_bukti_bayar(request.files.get('bukti'))
        except ValueError as error:
            flash(str(error), 'error')
            return redirect(
                url_for('bayar_qris', kode=transaksi.kode_pesanan)
            )

        bukti_lama = transaksi.bukti_bayar
        transaksi.bukti_bayar = bukti_baru
        transaksi.status_pembayaran = 'Menunggu Verifikasi'

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            hapus_file_bukti(bukti_baru)
            app.logger.exception('Gagal menyimpan bukti pembayaran QRIS')
            flash('Bukti pembayaran gagal disimpan. Coba lagi.', 'error')
            return redirect(
                url_for('bayar_qris', kode=transaksi.kode_pesanan)
            )

        if bukti_lama:
            hapus_file_bukti(bukti_lama)

        flash(
            'Bukti pembayaran terkirim dan menunggu verifikasi kasir.',
            'sukses'
        )
        return redirect(
            url_for('status_pesanan', kode=transaksi.kode_pesanan)
        )

    token = QRIS_DEMO_SIGNER.dumps(transaksi.kode_pesanan)
    qris_demo_url = (
        url_for(
            'selesaikan_pembayaran_qris_demo',
            kode=transaksi.kode_pesanan,
            token=token
        )
        if QRIS_DEMO_MODE else None
    )

    return render_template(
        'pembayaran_qris.html',
        transaksi=transaksi,
        qris_demo=QRIS_DEMO_MODE,
        qris_ada=os.path.isfile(os.path.join(
            app.static_folder, QRIS_IMAGE_FILENAME
        )),
        qris_filename=QRIS_IMAGE_FILENAME,
        qris_demo_url=qris_demo_url
    )


@app.route('/pesanan/<kode>/qris-demo.svg')
def qris_demo_image(kode):

    if not QRIS_DEMO_MODE:
        abort(404)

    transaksi = cari_pesanan_online(kode)
    if not transaksi or transaksi.metode_bayar != 'QRIS':
        abort(404)

    token = QRIS_DEMO_SIGNER.dumps(transaksi.kode_pesanan)
    target_url = url_for(
        'selesaikan_pembayaran_qris_demo',
        kode=transaksi.kode_pesanan,
        token=token,
        _external=True
    )

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    gambar = BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(gambar)
    return Response(
        gambar.getvalue(),
        mimetype='image/svg+xml',
        headers={'Cache-Control': 'no-store'}
    )


@app.route('/pesanan/<kode>/bayar/demo/<token>')
def selesaikan_pembayaran_qris_demo(kode, token):

    if not QRIS_DEMO_MODE:
        abort(404)

    transaksi = cari_pesanan_online(kode)
    if not transaksi or transaksi.metode_bayar != 'QRIS':
        abort(404)

    try:
        kode_tanda_tangan = QRIS_DEMO_SIGNER.loads(token)
    except BadSignature:
        abort(403)

    if kode_tanda_tangan != transaksi.kode_pesanan:
        abort(403)

    if transaksi.status_pembayaran != 'Lunas':
        transaksi.uang_diterima = transaksi.total_harga
        transaksi.kembalian = 0
        transaksi.status_pembayaran = 'Lunas'
        transaksi.waktu_bayar = datetime.now()
        if transaksi.status == 'Menunggu Pembayaran':
            transaksi.status = 'Diproses'
        db.session.commit()
        flash('Pembayaran QRIS demo berhasil. Pesanan mulai diproses.', 'sukses')

    return redirect(url_for('status_pesanan', kode=transaksi.kode_pesanan))


# ==========================================
# 14. MENJALANKAN APLIKASI
# ==========================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)