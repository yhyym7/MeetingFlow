"""Create an empty project database and save its URL only in local .env."""

import argparse
import getpass
import re
from pathlib import Path

import pymysql
from dotenv import set_key
from sqlalchemy import URL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--database", default="meetingflow")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", args.database):
        parser.error("Database name must contain only ASCII letters, digits and underscores.")

    password = getpass.getpass("MySQL password (hidden): ")
    try:
        connection = pymysql.connect(
            host=args.host, port=args.port, user=args.user, password=password,
            charset="utf8mb4", connect_timeout=5, read_timeout=15, write_timeout=15,
            autocommit=True,
        )
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                print(f"MySQL server: {cursor.fetchone()[0]}")
                cursor.execute(
                    "SELECT SCHEMA_NAME FROM information_schema.schemata WHERE SCHEMA_NAME=%s",
                    (args.database,),
                )
                if cursor.fetchone():
                    cursor.execute(f"SHOW TABLES FROM `{args.database}`")
                    if cursor.fetchone():
                        print("Database is not empty. No schema or local configuration changed.")
                        return 1
                print("Preparing the empty project database...", flush=True)
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{args.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
    except pymysql.MySQLError as exc:
        # Do not echo connection arguments, passwords or a full traceback.
        print(f"MySQL setup failed (error code {exc.args[0]}). Check local connection details.")
        return 1

    url = URL.create(
        "mysql+pymysql", username=args.user, password=password,
        host=args.host, port=args.port, database=args.database,
        query={"charset": "utf8mb4"},
    )
    env_path = Path(__file__).resolve().parents[1] / ".env"
    set_key(env_path, "MEETINGFLOW_DATABASE_URL", url.render_as_string(hide_password=False))
    print(f"Empty database '{args.database}' ready; connection saved in backend/.env (hidden).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
