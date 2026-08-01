-- Runs once on first container start (docker-entrypoint-initdb.d).
-- pytest-django creates/drops `test_metrodrip`; the default MYSQL_USER grant
-- only covers `metrodrip`, so extend it to the test databases.
CREATE DATABASE IF NOT EXISTS `metrodrip_inventory` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON `metrodrip%`.* TO 'metrodrip'@'%';
GRANT ALL PRIVILEGES ON `test\_metrodrip%`.* TO 'metrodrip'@'%';
FLUSH PRIVILEGES;
