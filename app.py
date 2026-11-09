
import json

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jotoast.db'
app.config['SECRET_KEY'] = 'jotoast_secret_123'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ==========================================
# FILTER FORMAT RUPIAH
# ==========================================

@app.template_filter('rupiah')
def format_rupiah(nilai):
    return "Rp{:,.0f}".format(nilai).replace(",", ".")


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
    status_ready = db.Column(db.Boolean, default=True)
    stok = db.Column(db.Integer, default=0, nullable=False)

    gambar = db.Column(db.String(500), nullable=True)

    kategori_id = db.Column(
        db.Integer,
        db.ForeignKey('kategori.id'),
        nullable=False
    )

class Transaksi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_pemesan = db.Column(db.String(100), nullable=True)
    metode_bayar = db.Column(db.String(20), nullable=False)
    total_harga = db.Column(db.Integer, nullable=False)

    # Membedakan transaksi online dan transaksi kasir
    sumber = db.Column(
        db.String(20),
        nullable=False,
        default='Kasir'
    )

    # Status pengerjaan pesanan
    status = db.Column(
        db.String(20),
        nullable=False,
        default='Menunggu'
    )


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
    harga = db.Column(db.Integer, nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Integer, nullable=False)


# ==========================================
# 2. MEMBUAT DAN MEMPERBARUI DATABASE
# ==========================================

with app.app_context():
    db.create_all()

    # Periksa kolom tabel transaksi
    kolom = {
        item['name']
        for item in inspect(db.engine).get_columns('transaksi')
    }

    if 'sumber' not in kolom:
        db.session.execute(text("""
            ALTER TABLE transaksi
            ADD COLUMN sumber VARCHAR(20) NOT NULL DEFAULT 'Kasir'
        """))

    if 'status' not in kolom:
        db.session.execute(text("""
            ALTER TABLE transaksi
            ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'Menunggu'
        """))

    # TAMBAHAN: Periksa kolom gambar pada tabel produk
    kolom_produk = {
        item['name']
        for item in inspect(db.engine).get_columns('produk')
    }

    if 'gambar' not in kolom_produk:
        db.session.execute(text("""
            ALTER TABLE produk
            ADD COLUMN gambar VARCHAR(500)
        """))

    # Simpan perubahan database
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

    produk = Produk.query.all()

    return render_template(
        'admin_produk.html',
        produk=produk
    )



@app.route('/admin/produk/tambah', methods=['GET', 'POST'])
def tambah_produk():

    if session.get('role') != 'owner':
        return redirect(url_for('login'))

    if request.method == 'POST':

        try:
            nama = request.form.get('nama', '').strip()
            harga = int(request.form.get('harga'))
            kategori_id = int(request.form.get('kategori_id'))
            stok = int(request.form.get('stok', 0))

            # AMBIL LINK GAMBAR
            gambar = request.form.get('gambar', '').strip()

            if not nama:
                raise ValueError('Nama produk harus diisi.')

            if harga < 0 or stok < 0:
                raise ValueError('Harga dan stok tidak boleh negatif!')

            produk_baru = Produk(
                nama=nama,
                harga=harga,
                kategori_id=kategori_id,
                stok=stok,
                status_ready=stok > 0,
                gambar=gambar if gambar else None
            )

            db.session.add(produk_baru)
            db.session.commit()

            flash('Produk berhasil ditambahkan.', 'sukses')

            return redirect(url_for('kelola_produk'))

        except (ValueError, TypeError):
            db.session.rollback()
            flash('Data produk tidak valid.', 'error')

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
            kategori_id = int(request.form.get('kategori_id'))
            stok = int(request.form.get('stok', 0))

            # AMBIL LINK GAMBAR BARU
            gambar = request.form.get('gambar', '').strip()

            if not nama:
                raise ValueError('Nama produk harus diisi.')

            if harga < 0 or stok < 0:
                raise ValueError('Harga dan stok tidak boleh negatif!')

            produk.nama = nama
            produk.harga = harga
            produk.kategori_id = kategori_id
            produk.stok = stok
            produk.status_ready = stok > 0

            # PERBARUI LINK GAMBAR
            produk.gambar = gambar if gambar else None

            db.session.commit()

            flash('Produk berhasil diperbarui.', 'sukses')

            return redirect(url_for('kelola_produk'))

        except (ValueError, TypeError):
            db.session.rollback()
            flash('Data produk tidak valid.', 'error')

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
                'error'
            )
        else:
            db.session.delete(kategori)
            db.session.commit()

    return redirect(url_for('kelola_kategori'))


# ==========================================
# 6. LOGOUT
# ==========================================

@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('menu_online'))


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
        transaksi_baru = Transaksi(
            nama_pemesan='Pelanggan Outlet',
            metode_bayar=metode_bayar,
            total_harga=total_harga,
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
            'sukses'
        )

        return redirect(url_for('kasir'))

    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:

        db.session.rollback()
        flash(str(e), 'error')

        return redirect(url_for('kasir'))

    except Exception:

        db.session.rollback()
        app.logger.exception('Gagal menyimpan transaksi kasir')

        flash(
            'Terjadi kesalahan saat menyimpan transaksi.',
            'error'
        )

        return redirect(url_for('kasir'))


# ==========================================
# 9. HALAMAN PESANAN ONLINE
# ==========================================

@app.route('/kasir/pesanan')
def pesanan_online():

    if session.get('role') != 'kasir':
        return redirect(url_for('login'))

    transaksi_list = (
        Transaksi.query
        .filter_by(sumber='Online')
        .order_by(Transaksi.id.desc())
        .all()
    )

    daftar_pesanan = []

    for transaksi in transaksi_list:

        detail = DetailTransaksi.query.filter_by(
            transaksi_id=transaksi.id
        ).all()

        daftar_pesanan.append({
            'transaksi': transaksi,
            'detail': detail
        })

    return render_template(
        'pesanan_online.html',
        daftar_pesanan=daftar_pesanan
    )


# ==========================================
# 10. TERIMA DAN SELESAIKAN PESANAN ONLINE
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

        flash('Pesanan tidak ditemukan.', 'error')

        return redirect(url_for('pesanan_online'))

    if aksi == 'terima' and transaksi.status == 'Menunggu':

        transaksi.status = 'Diproses'

        flash('Pesanan berhasil diterima.', 'sukses')

    elif aksi == 'selesai' and transaksi.status == 'Diproses':

        transaksi.status = 'Selesai'

        flash('Pesanan berhasil diselesaikan.', 'sukses')

    else:

        flash('Perubahan status tidak valid.', 'error')

        return redirect(url_for('pesanan_online'))

    db.session.commit()

    return redirect(url_for('pesanan_online'))


# ==========================================
# 11. MENU ONLINE PELANGGAN
# ==========================================

@app.route('/')
def menu_online():

    kategori_aktif = request.args.get('kategori', 'semua')

    if kategori_aktif == 'semua':

        produk = Produk.query.all()

    else:

        kategori = Kategori.query.filter_by(
            nama=kategori_aktif
        ).first()

        produk = (
            Produk.query.filter_by(kategori_id=kategori.id).all()
            if kategori else []
        )

    cart = session.get('cart', {})
    jumlah_keranjang = sum(cart.values())

    return render_template(
        'menu_online.html',
        produk=produk,
        cart=cart,
        jumlah_keranjang=jumlah_keranjang
    )


# ==========================================
# 12. KERANJANG BELANJA
# ==========================================

@app.route('/keranjang/tambah/<int:produk_id>', methods=['POST'])
def tambah_keranjang(produk_id):

    produk = Produk.query.get_or_404(produk_id)

    cart = session.get('cart', {})
    id_produk = str(produk_id)

    jumlah_sekarang = int(cart.get(id_produk, 0))

    if not produk.status_ready or produk.stok <= jumlah_sekarang:

        flash('Stok produk tidak mencukupi!', 'error')

        return redirect(request.referrer or url_for('menu_online'))

    cart[id_produk] = jumlah_sekarang + 1

    session['cart'] = cart
    session.modified = True

    flash(
        f'{produk.nama} ditambahkan ke keranjang.',
        'sukses'
    )

    return redirect(request.referrer or url_for('menu_online'))


@app.route('/keranjang/kurang/<int:produk_id>', methods=['POST'])
def kurang_keranjang(produk_id):

    cart = session.get('cart', {})
    id_produk = str(produk_id)

    if id_produk in cart:

        cart[id_produk] -= 1

        if cart[id_produk] <= 0:
            del cart[id_produk]

    session['cart'] = cart
    session.modified = True

    return redirect(url_for('checkout'))


@app.route('/keranjang/hapus/<int:produk_id>', methods=['POST'])
def hapus_keranjang(produk_id):

    cart = session.get('cart', {})
    id_produk = str(produk_id)

    cart.pop(id_produk, None)

    session['cart'] = cart
    session.modified = True

    return redirect(url_for('checkout'))


# ==========================================
# 13. CHECKOUT ONLINE PELANGGAN
# ==========================================

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():

    cart = session.get('cart', {})

    items = []
    total = 0

    # Ambil data produk dari database
    for id_produk, jumlah in cart.items():

        produk = db.session.get(Produk, int(id_produk))

        if produk and int(jumlah) > 0:

            subtotal = produk.harga * int(jumlah)

            items.append({
                'produk': produk,
                'jumlah': int(jumlah),
                'subtotal': subtotal
            })

            total += subtotal

    # Periksa keranjang kosong
    if not items:

        flash('Keranjang masih kosong.', 'error')

        return render_template(
            'checkout.html',
            items=[],
            total=0
        )

    # Proses checkout
    if request.method == 'POST':

        nama_pemesan = request.form.get(
            'nama_pemesan', ''
        ).strip()

        metode_bayar = request.form.get(
            'metode_bayar', ''
        ).strip()

        if not nama_pemesan:

            flash('Nama pemesan harus diisi.', 'error')

            return redirect(url_for('checkout'))

        if not metode_bayar:

            flash('Silakan pilih metode pembayaran.', 'error')

            return redirect(url_for('checkout'))

        try:

            # Periksa stok terbaru sebelum transaksi
            for item in items:

                produk = item['produk']

                if produk.stok < item['jumlah']:

                    raise ValueError(
                        f'Stok {produk.nama} tidak mencukupi.'
                    )

                if not produk.status_ready:

                    raise ValueError(
                        f'{produk.nama} sedang tidak tersedia.'
                    )

            # Simpan transaksi online
            transaksi_baru = Transaksi(
                nama_pemesan=nama_pemesan,
                metode_bayar=metode_bayar,
                total_harga=total,
                sumber='Online',
                status='Menunggu'
            )

            db.session.add(transaksi_baru)
            db.session.flush()

            # Simpan rincian makanan dan kurangi stok
            for item in items:

                produk = item['produk']

                detail = DetailTransaksi(
                    transaksi_id=transaksi_baru.id,
                    produk_id=produk.id,
                    nama_produk=produk.nama,
                    harga=produk.harga,
                    jumlah=item['jumlah'],
                    subtotal=item['subtotal']
                )

                db.session.add(detail)

                produk.stok -= item['jumlah']
                produk.status_ready = produk.stok > 0

            db.session.commit()

            # Kosongkan keranjang setelah berhasil
            session.pop('cart', None)

            flash(
                'Pesanan berhasil dibuat! Pesanan akan diterima kasir.',
                'sukses'
            )

            return redirect(url_for('menu_online'))

        except ValueError as e:

            db.session.rollback()

            flash(str(e), 'error')

            return redirect(url_for('checkout'))

        except Exception:

            db.session.rollback()

            app.logger.exception('Gagal menyimpan checkout online')

            flash(
                'Terjadi kesalahan saat menyimpan pesanan.',
                'error'
            )

            return redirect(url_for('checkout'))

    return render_template(
        'checkout.html',
        items=items,
        total=total
    )


# ==========================================
# 14. MENJALANKAN APLIKASI
# ==========================================

if __name__ == '__main__':
    app.run(debug=True)
