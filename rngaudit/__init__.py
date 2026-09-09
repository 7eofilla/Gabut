"""
rngaudit - toolkit forensik untuk mengaudit keadilan (fairness) sebuah RNG
dan menjawab satu pertanyaan: "saya rugi karena sial, atau karena dicurangi?"

Filosofi:
  Kita TIDAK mencari "pola untuk menang". Kita mencari BUKTI STATISTIK bahwa
  sebuah urutan angka menyimpang dari acak murni. Itu dua hal yang berbeda:
  RNG yang sudah terbukti menyimpang pun belum tentu bisa diprediksi.

Setiap tes mengembalikan p-value. Baca p-value seperti ini:
  p = probabilitas melihat data seaneh ini ATAU LEBIH ANEH, KALAU RNG-nya jujur.
  p kecil  -> data ini aneh untuk RNG jujur -> curiga.
  p besar  -> data ini normal untuk RNG jujur -> tidak ada bukti curang.

  p besar BUKAN bukti bahwa RNG-nya jujur. Itu cuma berarti "belum ketahuan".
"""

__version__ = "0.1.0"
