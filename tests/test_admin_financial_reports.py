import os
import re
import unittest
from datetime import datetime

os.environ['JOTOAST_DB'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    DetailTransaksi,
    Kategori,
    Produk,
    Transaksi,
    app,
    db,
)


class AdminFinancialReportTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.kategori = Kategori(nama='Coffee')
            db.session.add(self.kategori)
            db.session.flush()
            self.kategori_id = self.kategori.id
            self.produk = Produk(
                nama='Kopi Susu',
                harga=10000,
                harga_modal=6000,
                kategori_id=self.kategori.id,
                stok=10,
                status_ready=True
            )
            db.session.add(self.produk)
            db.session.commit()
            self.produk_id = self.produk.id
        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_profit_report_only_counts_known_snapshot_costs(self):
        now = datetime.now()
        with app.app_context():
            transaksi_lengkap = Transaksi(
                metode_bayar='Tunai',
                status_pembayaran='Lunas',
                total_harga=20000,
                waktu_bayar=now,
                tanggal_waktu=now
            )
            transaksi_lama = Transaksi(
                metode_bayar='Tunai',
                status_pembayaran='Lunas',
                total_harga=5000,
                waktu_bayar=now,
                tanggal_waktu=now
            )
            db.session.add_all([transaksi_lengkap, transaksi_lama])
            db.session.flush()
            db.session.add_all([
                DetailTransaksi(
                    transaksi_id=transaksi_lengkap.id,
                    produk_id=self.produk_id,
                    nama_produk='Kopi Susu',
                    harga=10000,
                    harga_modal=6000,
                    jumlah=2,
                    subtotal=20000
                ),
                DetailTransaksi(
                    transaksi_id=transaksi_lama.id,
                    produk_id=self.produk_id,
                    nama_produk='Kopi Susu',
                    harga=5000,
                    harga_modal=None,
                    jumlah=1,
                    subtotal=5000
                )
            ])
            db.session.commit()

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        bulan = now.strftime('%Y-%m')
        response = self.client.get(f'/admin/pendapatan?bulan={bulan}')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Rp25.000', html)
        self.assertIn('Rp12.000', html)
        self.assertIn('Rp8.000', html)
        self.assertIn('1 transaksi lunas memiliki harga modal', html)
        self.assertIn('2 dari 3 unit', html)

    def test_income_report_supports_all_time_and_month_filters(self):
        now = datetime.now()
        with app.app_context():
            transaksi_bulan_ini = Transaksi(
                metode_bayar='Tunai',
                status_pembayaran='Lunas',
                total_harga=10000,
                waktu_bayar=now,
                tanggal_waktu=now
            )
            transaksi_lama = Transaksi(
                metode_bayar='Tunai',
                status_pembayaran='Lunas',
                total_harga=5000,
                waktu_bayar=None,
                tanggal_waktu=None
            )
            db.session.add_all([transaksi_bulan_ini, transaksi_lama])
            db.session.flush()
            transaksi_lama.tanggal_waktu = None
            db.session.add_all([
                DetailTransaksi(
                    transaksi_id=transaksi_bulan_ini.id,
                    produk_id=self.produk_id,
                    nama_produk='Kopi Susu',
                    harga=10000,
                    harga_modal=6000,
                    jumlah=1,
                    subtotal=10000
                ),
                DetailTransaksi(
                    transaksi_id=transaksi_lama.id,
                    produk_id=self.produk_id,
                    nama_produk='Kopi Susu',
                    harga=5000,
                    harga_modal=3000,
                    jumlah=1,
                    subtotal=5000
                )
            ])
            db.session.commit()

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        response = self.client.get('/admin/pendapatan?mode=keseluruhan')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Semua Periode', html)
        self.assertIn('Rp15.000', html)
        self.assertIn('Rp9.000', html)
        self.assertIn('Rp6.000', html)
        self.assertIn('<strong>2</strong>', html)

        response = self.client.get(
            '/admin/pendapatan?mode=bulan&bulan={}'.format(
                now.strftime('%Y-%m')
            )
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Rp10.000', html)
        self.assertIn('Rp6.000', html)
        self.assertIn('Rp4.000', html)
        self.assertIn('<strong>1</strong>', html)

    def test_sales_report_shows_daily_and_monthly_recap(self):
        now = datetime.now()
        with app.app_context():
            transaksi = Transaksi(
                metode_bayar='Tunai',
                status_pembayaran='Lunas',
                total_harga=10000,
                waktu_bayar=now,
                tanggal_waktu=now
            )
            db.session.add(transaksi)
            db.session.flush()
            db.session.add(DetailTransaksi(
                transaksi_id=transaksi.id,
                produk_id=self.produk_id,
                nama_produk='Kopi Susu',
                harga=10000,
                harga_modal=6000,
                jumlah=1,
                subtotal=10000
            ))
            db.session.commit()

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        response = self.client.get(
            f'/admin/laporan-penjualan?bulan={now.strftime("%Y-%m")}'
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Periode laporan', html)
        self.assertNotIn('Pilih bulan laporan', html)
        self.assertIn('Rincian Harian', html)
        self.assertIn('Rekap Bulanan — 12 Bulan Terakhir', html)
        self.assertEqual(html.count('admin-table-scroll admin-report-scroll'), 2)
        for column in (
            'tanggal pembayaran diterima',
            'jumlah transaksi dengan status pembayaran Lunas',
            'total nilai transaksi lunas',
            'hanya untuk item yang harga modalnya diketahui',
            'harga modal yang belum tercatat'
        ):
            self.assertIn(column, html)
        tanggal = now.strftime('%d-%m-%Y')
        self.assertRegex(
            html,
            re.compile(
                rf'<td>{tanggal}</td>\s*<td>1</td>\s*'
                r'<td>Rp10\.000</td>\s*<td>Rp4\.000</td>'
            )
        )

    def test_cashier_transaction_saves_cost_snapshot(self):
        with self.client.session_transaction() as session:
            session['role'] = 'kasir'
        response = self.client.post(
            '/kasir/proses_transaksi',
            data={
                'items_json': f'[{{"id": {self.produk_id}, "jumlah": 2}}]',
                'metode_bayar': 'Tunai',
                'uang_diterima': '20000'
            }
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            detail = DetailTransaksi.query.one()
            self.assertEqual(detail.harga_modal, 6000)

    def test_online_checkout_saves_cost_snapshot(self):
        with self.client.session_transaction() as session:
            session['cart'] = {f'{self.produk_id}-0': 2}
        response = self.client.post(
            '/checkout',
            data={'nama_pemesan': 'Pelanggan Uji', 'metode_bayar': 'Tunai'}
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            detail = DetailTransaksi.query.one()
            self.assertEqual(detail.harga_modal, 6000)
            self.assertEqual(detail.jumlah, 2)

    def test_owner_can_set_product_cost_and_negative_cost_is_rejected(self):
        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        response = self.client.post(
            '/admin/produk/edit/{}'.format(self.produk_id),
            data={
                'nama': 'Kopi Susu',
                'harga': '10000',
                'harga_modal': '7000',
                'kategori_id': str(self.kategori_id),
                'stok': '10'
            }
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(db.session.get(Produk, self.produk_id).harga_modal, 7000)

        response = self.client.post(
            '/admin/produk/edit/{}'.format(self.produk_id),
            data={
                'nama': 'Kopi Susu',
                'harga': '10000',
                'harga_modal': '-1',
                'kategori_id': str(self.kategori_id),
                'stok': '10'
            }
        )
        self.assertEqual(response.status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.get(Produk, self.produk_id).harga_modal, 7000)

    def test_setting_product_cost_backfills_old_transaction_lines(self):
        now = datetime.now()
        with app.app_context():
            transaksi = Transaksi(
                metode_bayar='Tunai',
                status_pembayaran='Lunas',
                total_harga=10000,
                waktu_bayar=now,
                tanggal_waktu=now
            )
            db.session.add(transaksi)
            db.session.flush()
            db.session.add(DetailTransaksi(
                transaksi_id=transaksi.id,
                produk_id=self.produk_id,
                nama_produk='Kopi Susu',
                harga=10000,
                harga_modal=None,
                jumlah=1,
                subtotal=10000
            ))
            db.session.commit()

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        response = self.client.post(
            '/admin/produk/edit/{}'.format(self.produk_id),
            data={
                'nama': 'Kopi Susu',
                'harga': '10000',
                'harga_modal': '6000',
                'kategori_id': str(self.kategori_id),
                'stok': '10'
            }
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            detail = DetailTransaksi.query.one()
            self.assertEqual(detail.harga_modal, 6000)

        response = self.client.get(
            '/admin/pendapatan?bulan={}'.format(now.strftime('%Y-%m'))
        )
        self.assertIn('Rp6.000', response.get_data(as_text=True))
        self.assertIn('Rp4.000', response.get_data(as_text=True))

    def test_reports_require_owner_and_reject_invalid_month(self):
        for path in (
            '/admin/pendapatan',
            '/admin/laporan-penjualan',
            '/admin/diagram'
        ):
            self.assertEqual(self.client.get(path).status_code, 302)

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        for path in (
            '/admin/pendapatan',
            '/admin/laporan-penjualan',
            '/admin/diagram'
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)

        with self.client.session_transaction() as session:
            session['role'] = 'kasir'
        for path in (
            '/admin/pendapatan',
            '/admin/laporan-penjualan',
            '/admin/diagram'
        ):
            self.assertEqual(self.client.get(path).status_code, 302, path)

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        response = self.client.get('/admin/laporan-penjualan?bulan=2026-13')
        self.assertEqual(response.status_code, 400)

    def test_product_and_category_pages_share_admin_navigation_layout(self):
        with self.client.session_transaction() as session:
            session['role'] = 'owner'

        for path in ('/admin/produk', '/admin/kategori'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertEqual(html.count('<main class="admin-main">'), 1)
                self.assertEqual(html.count('class="admin-nav-link'), 6)
                self.assertIn('aria-current="page"', html)
                self.assertIn('href="/admin/diagram"', html)
                self.assertIn('href="/admin/pendapatan"', html)

    def test_admin_pages_have_return_home_button(self):
        with self.client.session_transaction() as session:
            session['role'] = 'owner'

        for path in (
            '/admin/diagram',
            '/admin/pendapatan',
            '/admin/laporan-penjualan',
            '/riwayat-transaksi'
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    'href="/" class="admin-back-link"',
                    response.get_data(as_text=True)
                )

    def test_admin_diagram_renders_vertical_sales_bars(self):
        now = datetime.now()
        with app.app_context():
            db.session.add_all([
                Transaksi(
                    metode_bayar='QRIS',
                    status_pembayaran='Lunas',
                    sumber='Online',
                    total_harga=15000,
                    tanggal_waktu=now,
                    waktu_bayar=now
                ),
                Transaksi(
                    metode_bayar='Tunai',
                    status_pembayaran='Belum Dibayar',
                    sumber='Kasir',
                    total_harga=10000,
                    tanggal_waktu=now
                )
            ])
            db.session.commit()

        with self.client.session_transaction() as session:
            session['role'] = 'owner'
        response = self.client.get('/admin/diagram')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('admin-sales-bars', html)
        self.assertEqual(html.count('class="admin-sales-bar"'), 7)
        self.assertEqual(html.count('class="admin-donut"'), 1)
        self.assertIn('conic-gradient(', html)
        self.assertEqual(html.count('class="admin-chart-track"'), 3)


if __name__ == '__main__':
    unittest.main()
