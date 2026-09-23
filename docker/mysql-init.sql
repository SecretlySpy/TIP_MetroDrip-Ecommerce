-- Runs once on first container start (docker-entrypoint-initdb.d).
-- pytest-django creates/drops `test_metrodrip`; the default MYSQL_USER grant
-- only covers `metrodrip`, so extend it to the test databases.
CREATE DATABASE IF NOT EXISTS `metrodrip_inventory` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON `metrodrip%`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_metrodrip%`.* TO 'metrodrip'@'%';
FLUSH PRIVILEGES;

-- Run with a migration administrator before starting the five-schema build.
-- Does not move or delete any existing tables or data.
CREATE DATABASE IF NOT EXISTS db_identity CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_catalog CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_orders CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_fulfillment CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_content CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

GRANT ALL PRIVILEGES ON `db_identity`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_db_identity`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `db_catalog`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_db_catalog`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `db_orders`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_db_orders`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `db_fulfillment`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_db_fulfillment`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `db_content`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_db_content`.* TO 'metrodrip'@'%';
