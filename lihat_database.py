import sqlite3

# Membuka database
conn = sqlite3.connect("instance/jotoast.db")
cursor = conn.cursor()

# Melihat semua tabel
cursor.execute("""
    SELECT name FROM sqlite_master
    WHERE type='table'
""")

tabel = cursor.fetchall()

print("DAFTAR TABEL:")
for t in tabel:
    print(t[0])

# Melihat data transaksi
cursor.execute("SELECT * FROM transaksi")
data = cursor.fetchall()

print("\nDATA TRANSAKSI:")
for row in data:
    print(row)

conn.close()