"""
database.py — PostgreSQL Schema & Connection for HeavyLift CRM
"""
import psycopg2, psycopg2.extras
from config import Config
from security import hash_password

def get_db():
    return psycopg2.connect(
        host=Config.DB_HOST, port=Config.DB_PORT,
        dbname=Config.DB_NAME, user=Config.DB_USER,
        password=Config.DB_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def close_db(conn, commit=True):
    if conn:
        if commit: conn.commit()
        conn.close()


def bootstrap_user(username=None, email=None, password=None, role=None):
    username = (username or Config.BOOTSTRAP_USERNAME).strip()
    email = (email or Config.BOOTSTRAP_EMAIL).strip()
    password = password or Config.BOOTSTRAP_PASSWORD
    role = (role or Config.BOOTSTRAP_ROLE).strip().lower()

    if not (username and email and password):
        return False
    if role not in {"teacher", "admin", "developer"}:
        raise ValueError("BOOTSTRAP_ROLE must be teacher, admin, or developer.")

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=%s OR email=%s LIMIT 1;", (username, email))
        if cur.fetchone():
            return False
        cur.execute(
            """
            INSERT INTO users (username,email,password_hash,role)
            VALUES (%s,%s,%s,%s);
            """,
            (username, email, hash_password(password), role),
        )
        conn.commit()
        return True
    finally:
        cur.close()
        conn.close()

def init_db():
    conn = get_db(); cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      VARCHAR(80)  UNIQUE NOT NULL,
            email         VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role          VARCHAR(20)  NOT NULL DEFAULT 'admin',
            location_id   INTEGER,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until  TIMESTAMP,
            last_failed_login_at TIMESTAMP,
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT role_chk CHECK (role IN ('teacher','admin','developer'))
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            description TEXT,
            location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            fees        NUMERIC(10,2) NOT NULL DEFAULT 0,
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id             SERIAL PRIMARY KEY,
            name           VARCHAR(100) NOT NULL,
            description    TEXT,
            discount_type  VARCHAR(10) NOT NULL DEFAULT 'flat',
            discount_value NUMERIC(10,2) NOT NULL DEFAULT 0,
            valid_from     DATE,
            valid_to       DATE,
            location_id    INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT dtype_chk CHECK (discount_type IN ('flat','percent'))
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(120) NOT NULL,
            gender           VARCHAR(10),
            mobile           VARCHAR(20)  NOT NULL,
            location_id      INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            city             VARCHAR(80),
            state            VARCHAR(80),
            course_id        INTEGER REFERENCES courses(id) ON DELETE SET NULL,
            offer_id         INTEGER REFERENCES offers(id) ON DELETE SET NULL,
            inquiry_date     DATE NOT NULL DEFAULT CURRENT_DATE,
            followup_date    DATE,
            admission_date   DATE,
            status           VARCHAR(20) NOT NULL DEFAULT 'Open',
            fees_total       NUMERIC(10,2) DEFAULT 0,
            fees_paid        NUMERIC(10,2) DEFAULT 0,
            ref1_name        VARCHAR(100),
            ref1_mobile      VARCHAR(20),
            ref2_name        VARCHAR(100),
            ref2_mobile      VARCHAR(20),
            ref3_name        VARCHAR(100),
            ref3_mobile      VARCHAR(20),
            assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT status_chk CHECK (status IN ('Open','Converted','Closed'))
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS followups (
            id             SERIAL PRIMARY KEY,
            inquiry_id     INTEGER NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
            conversation   TEXT,
            followup_date  DATE,
            status         VARCHAR(20) NOT NULL DEFAULT 'Open',
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_msgs (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL,
            description TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          SERIAL PRIMARY KEY,
            title       VARCHAR(200) NOT NULL,
            message     TEXT,
            target_role VARCHAR(20),
            is_read     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)

    # Performance indexes for the most common production queries.
    for sql in [
        "CREATE INDEX IF NOT EXISTS idx_inquiries_location_id ON inquiries(location_id)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_course_id ON inquiries(course_id)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_status ON inquiries(status)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_inquiry_date ON inquiries(inquiry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_followup_date ON inquiries(followup_date)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_location_status_followup ON inquiries(location_id, status, followup_date)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_course_inquiry_date ON inquiries(course_id, inquiry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_inquiries_location_inquiry_date ON inquiries(location_id, inquiry_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_followups_inquiry_id_created_at ON followups(inquiry_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_notifications_role_read_created_at ON notifications(target_role, is_read, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_courses_location_position ON courses(location_id, position, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_locations_position_created_at ON locations(position, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_offers_location_active_valid_to ON offers(location_id, is_active, valid_to)",
    ]:
        cur.execute(sql)

    # Safe migrations for existing DBs
    for sql in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_failed_login_at TIMESTAMP",
        "ALTER TABLE locations ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE courses   ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS gender VARCHAR(10)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS city VARCHAR(80)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS state VARCHAR(80)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS course_id INTEGER REFERENCES courses(id) ON DELETE SET NULL",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS offer_id INTEGER REFERENCES offers(id) ON DELETE SET NULL",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS followup_date DATE",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS admission_date DATE",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'Open'",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS fees_total NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS fees_paid  NUMERIC(10,2) DEFAULT 0",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref1_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref2_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_name VARCHAR(100)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS ref3_mobile VARCHAR(20)",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE inquiries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()",
    ]:
        try:
            cur.execute(sql); conn.commit()
        except Exception:
            conn.rollback()

    conn.commit(); cur.close(); conn.close()
    print("HeavyLift CRM database ready.")
