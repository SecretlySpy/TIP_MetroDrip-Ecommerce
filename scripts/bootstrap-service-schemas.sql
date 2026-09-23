-- Run with a migration administrator before starting the five-schema build.
-- Does not move or delete any existing tables or data.
CREATE DATABASE IF NOT EXISTS db_identity CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_catalog CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_orders CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_fulfillment CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS db_content CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
