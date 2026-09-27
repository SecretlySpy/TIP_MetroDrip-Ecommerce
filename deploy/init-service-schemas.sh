#!/bin/sh
# Sourced by the official MySQL image on an empty volume. Existing deployments
# run this manually as a maintenance/bootstrap step before transferring data.
(
set -eu
case "$MYSQL_USER" in
  ''|*[!a-zA-Z0-9_]*) echo 'MYSQL_USER must contain only letters, digits or underscores' >&2; exit 1 ;;
esac
for schema in db_identity db_catalog db_orders db_fulfillment db_content; do
  MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --user=root <<SQL
CREATE DATABASE IF NOT EXISTS \`$schema\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON \`$schema\`.* TO '$MYSQL_USER'@'%';
SQL
done

)
