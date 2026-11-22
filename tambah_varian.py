# Jalankan sekali: python tambah_varian.py
# Mengisi contoh varian untuk produk yang sudah ada.
from app import app, db, Produk, Kategori, Varian

CONTOH = {
    'Coffee':    [('Panas', 0), ('Dingin', 2000)],
    'Rice Bowl': [('Tidak Pedas', 0), ('Pedas', 0), ('Extra Telur', 3000)],
    'Toast':     [('Original', 0), ('Extra Keju', 3000)],
}

with app.app_context():
    for nama_kategori, daftar in CONTOH.items():
        kategori = Kategori.query.filter_by(nama=nama_kategori).first()
        if not kategori:
            continue
        for produk in Produk.query.filter_by(kategori_id=kategori.id).all():
            if produk.varian:
                continue  # jangan duplikat
            for nama, tambahan in daftar:
                db.session.add(Varian(
                    produk_id=produk.id, nama=nama, harga_tambahan=tambahan
                ))
    db.session.commit()
    print('Varian berhasil ditambahkan.')