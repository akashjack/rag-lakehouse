-- Idempotent bootstrap of the application user 'rag' on FREEPDB1.
-- Safe to re-run: catches ORA-01920 (user already exists).
--
-- Why RESOURCE role: in 23ai, you cannot directly grant CREATE INDEX,
-- CREATE VIEW etc. as system privileges (ORA-00990). The RESOURCE role
-- includes them. CONNECT + RESOURCE is the canonical "ordinary app user"
-- privilege set.

WHENEVER SQLERROR EXIT 1

DECLARE
    e_user_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_user_exists, -1920);
BEGIN
    EXECUTE IMMEDIATE 'CREATE USER rag IDENTIFIED BY RagApp_2026
        DEFAULT TABLESPACE USERS
        TEMPORARY TABLESPACE TEMP
        QUOTA UNLIMITED ON USERS';
EXCEPTION
    WHEN e_user_exists THEN
        DBMS_OUTPUT.PUT_LINE('User RAG already exists — skipping CREATE.');
END;
/

-- Core privileges via roles (RESOURCE includes CREATE TABLE/VIEW/INDEX/etc.)
GRANT CONNECT, RESOURCE TO rag;

-- Oracle Text for Phase 4 hybrid retrieval (CONTEXT index on chunk_text)
GRANT CTXAPP                       TO rag;
GRANT EXECUTE ON CTXSYS.CTX_DDL    TO rag;

-- Ensure tablespace quota survives re-runs
ALTER USER rag QUOTA UNLIMITED ON USERS;

-- Verify
SELECT username, default_tablespace FROM dba_users WHERE username = 'RAG';

EXIT
