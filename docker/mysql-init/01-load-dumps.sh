#!/bin/bash
set -euo pipefail

DUMP_DIR=/sql-dumps
MYSQL="mysql -uroot -p${MYSQL_ROOT_PASSWORD}"

echo "[init] Creating databases wallet_db and partner_db..."
${MYSQL} <<SQL
CREATE DATABASE IF NOT EXISTS wallet_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS partner_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON wallet_db.* TO '${MYSQL_USER}'@'%';
GRANT ALL PRIVILEGES ON partner_db.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL

echo "[init] Loading wallet_db dumps..."
for f in \
  "${DUMP_DIR}/wallet_db_accounts.sql" \
  "${DUMP_DIR}/wallet_db_bank_accounts.sql" \
  "${DUMP_DIR}/wallet_db_transactions.sql" \
  "${DUMP_DIR}/wallet_db_transactions_devises.sql"; do
  echo "  -> $(basename "$f")"
  ${MYSQL} wallet_db < "$f"
done

echo "[init] Loading partner_db dumps..."
for f in \
  "${DUMP_DIR}/partner_db_orders.sql" \
  "${DUMP_DIR}/partner_db_ria_transactions.sql"; do
  echo "  -> $(basename "$f")"
  ${MYSQL} partner_db < "$f"
done

echo "[init] Done."
