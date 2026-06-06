-- ============================================================
-- Q2P Platform — Complete MySQL Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS q2p_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE q2p_db;

-- ─────────────────────────────── USERS ───────────────────────────────
CREATE TABLE users (
    id            VARCHAR(36)  PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          ENUM('SUPER_ADMIN','BANKER','CUSTOMER','UNDERWRITER','COMPLIANCE','OPS_ADMIN') NOT NULL,
    phone         VARCHAR(20),
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_users_email (email),
    INDEX idx_users_role  (role)
);

-- ─────────────────────────────── CASES ───────────────────────────────
CREATE TABLE cases (
    id                VARCHAR(36) PRIMARY KEY,
    case_number       VARCHAR(50) NOT NULL UNIQUE,
    customer_id       VARCHAR(36) NOT NULL,
    banker_id         VARCHAR(36) NOT NULL,
    current_stage     ENUM(
        'CUSTOMER_INTAKE','NEEDS_ANALYSIS','SUITABILITY_VALIDATION',
        'QUOTE_RETRIEVAL','QUOTE_COMPARISON','RECOMMENDATION',
        'BANKER_APPROVAL','OTP_CONSENT','PROPOSAL_GENERATION',
        'MEDICAL_COORDINATION','UNDERWRITING','POLICY_ISSUANCE',
        'EXCEPTION_HANDLING','ESCALATION','COMPLETED'
    ) NOT NULL DEFAULT 'CUSTOMER_INTAKE',
    status            ENUM('ACTIVE','PENDING','ON_HOLD','COMPLETED','CANCELLED','ESCALATED') NOT NULL DEFAULT 'ACTIVE',
    customer_profile  JSON,
    needs_analysis    JSON,
    suitability_result JSON,
    recommendation    JSON,
    sum_assured       DECIMAL(15,2),
    premium_budget    DECIMAL(15,2),
    policy_tenure     INT,
    banker_approved   TINYINT(1)  DEFAULT 0,
    banker_remarks    TEXT,
    banker_approved_at DATETIME,
    consent_given     TINYINT(1)  DEFAULT 0,
    consent_given_at  DATETIME,
    stage_entered_at  DATETIME    DEFAULT CURRENT_TIMESTAMP,
    last_activity_at  DATETIME    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (banker_id)   REFERENCES users(id),
    INDEX idx_cases_customer  (customer_id),
    INDEX idx_cases_banker    (banker_id),
    INDEX idx_cases_stage     (current_stage),
    INDEX idx_cases_status    (status)
);

-- ─────────────────────────────── QUOTES ──────────────────────────────
CREATE TABLE quotes (
    id                       VARCHAR(36)    PRIMARY KEY,
    case_id                  VARCHAR(36)    NOT NULL,
    insurer_code             VARCHAR(50)    NOT NULL,
    insurer_name             VARCHAR(200)   NOT NULL,
    product_name             VARCHAR(200)   NOT NULL,
    product_code             VARCHAR(100)   NOT NULL,
    annual_premium           DECIMAL(12,2)  NOT NULL,
    sum_assured              DECIMAL(15,2)  NOT NULL,
    policy_tenure            INT            NOT NULL,
    premium_frequency        VARCHAR(50)    DEFAULT 'ANNUAL',
    coverage_details         JSON,
    riders                   JSON,
    exclusions               JSON,
    waiting_period_days      INT,
    underwriting_requirements JSON,
    medical_requirements     JSON,
    ai_rank                  INT,
    ai_score                 DECIMAL(5,4),
    ai_recommendation_text   TEXT,
    raw_response             JSON,
    status                   ENUM('PENDING','RETRIEVED','SELECTED','REJECTED','EXPIRED') DEFAULT 'RETRIEVED',
    retrieved_at             DATETIME       DEFAULT CURRENT_TIMESTAMP,
    expires_at               DATETIME,
    created_at               DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
    INDEX idx_quotes_case    (case_id),
    INDEX idx_quotes_insurer (insurer_code)
);

-- ─────────────────────────────── POLICIES ────────────────────────────
CREATE TABLE policies (
    id                   VARCHAR(36)   PRIMARY KEY,
    case_id              VARCHAR(36)   NOT NULL UNIQUE,
    quote_id             VARCHAR(36)   NOT NULL,
    customer_id          VARCHAR(36)   NOT NULL,
    policy_number        VARCHAR(100)  UNIQUE,
    insurer_code         VARCHAR(50)   NOT NULL,
    insurer_name         VARCHAR(200)  NOT NULL,
    product_name         VARCHAR(200)  NOT NULL,
    product_code         VARCHAR(100)  NOT NULL,
    annual_premium       DECIMAL(12,2) NOT NULL,
    sum_assured          DECIMAL(15,2) NOT NULL,
    policy_tenure        INT           NOT NULL,
    premium_frequency    VARCHAR(50)   DEFAULT 'ANNUAL',
    status               ENUM('DRAFT','SUBMITTED','UNDER_REVIEW','APPROVED','ISSUED','REJECTED','LAPSED','CANCELLED') DEFAULT 'DRAFT',
    proposal_data        JSON,
    proposal_submitted_at DATETIME,
    issued_at            DATETIME,
    uw_status            VARCHAR(50),
    uw_remarks           TEXT,
    uw_reviewed_by       VARCHAR(36),
    uw_reviewed_at       DATETIME,
    compliance_checked   TINYINT(1)   DEFAULT 0,
    compliance_remarks   TEXT,
    policy_document_path VARCHAR(500),
    commencement_date    DATETIME,
    maturity_date        DATETIME,
    created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id)     REFERENCES cases(id),
    FOREIGN KEY (quote_id)    REFERENCES quotes(id),
    FOREIGN KEY (customer_id) REFERENCES users(id),
    INDEX idx_policies_customer (customer_id),
    INDEX idx_policies_status   (status)
);

-- ─────────────────────────────── OTP ─────────────────────────────────
CREATE TABLE otp_records (
    id           VARCHAR(36) PRIMARY KEY,
    case_id      VARCHAR(36) NOT NULL,
    customer_id  VARCHAR(36) NOT NULL,
    otp_hash     VARCHAR(255) NOT NULL,
    status       ENUM('PENDING','VERIFIED','EXPIRED','INVALIDATED') DEFAULT 'PENDING',
    purpose      VARCHAR(100) DEFAULT 'CONSENT',
    retry_count  INT DEFAULT 0,
    resend_count INT DEFAULT 0,
    expires_at   DATETIME NOT NULL,
    verified_at  DATETIME,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id)     REFERENCES cases(id),
    FOREIGN KEY (customer_id) REFERENCES users(id),
    INDEX idx_otp_case     (case_id),
    INDEX idx_otp_customer (customer_id),
    INDEX idx_otp_status   (status)
);

CREATE TABLE otp_audit_logs (
    id          VARCHAR(36) PRIMARY KEY,
    otp_id      VARCHAR(36) NOT NULL,
    case_id     VARCHAR(36) NOT NULL,
    customer_id VARCHAR(36) NOT NULL,
    action      VARCHAR(100) NOT NULL,
    ip_address  VARCHAR(50),
    user_agent  VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (otp_id) REFERENCES otp_records(id),
    INDEX idx_otp_audit_otp  (otp_id),
    INDEX idx_otp_audit_case (case_id)
);

-- ─────────────────────────────── CONSENT ─────────────────────────────
CREATE TABLE consent_records (
    id             VARCHAR(36) PRIMARY KEY,
    case_id        VARCHAR(36) NOT NULL,
    customer_id    VARCHAR(36) NOT NULL,
    otp_record_id  VARCHAR(36),
    consent_type   VARCHAR(100) DEFAULT 'POLICY_CONSENT',
    consent_text   TEXT,
    ip_address     VARCHAR(50),
    user_agent     VARCHAR(500),
    consented_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id)     REFERENCES cases(id),
    FOREIGN KEY (customer_id) REFERENCES users(id),
    INDEX idx_consent_case     (case_id),
    INDEX idx_consent_customer (customer_id)
);

-- ─────────────────────────────── ESCALATIONS ─────────────────────────
CREATE TABLE escalation_rules (
    id              VARCHAR(36)  PRIMARY KEY,
    stage           VARCHAR(100) NOT NULL,
    interval_minutes INT         NOT NULL DEFAULT 10,
    level_1_role    VARCHAR(100),
    level_2_role    VARCHAR(100),
    level_3_role    VARCHAR(100),
    is_active       TINYINT(1)   DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE escalation_logs (
    id               VARCHAR(36) PRIMARY KEY,
    case_id          VARCHAR(36) NOT NULL,
    escalation_level ENUM('LEVEL_1','LEVEL_2','LEVEL_3') DEFAULT 'LEVEL_1',
    stage            VARCHAR(100) NOT NULL,
    reason           TEXT,
    assigned_to_role VARCHAR(100),
    assigned_to_user VARCHAR(36),
    notified         TINYINT(1) DEFAULT 0,
    resolved         TINYINT(1) DEFAULT 0,
    resolved_at      DATETIME,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id),
    INDEX idx_esc_case     (case_id),
    INDEX idx_esc_resolved (resolved)
);

-- ─────────────────────────────── SMTP CONFIG ─────────────────────────
CREATE TABLE smtp_configs (
    id          VARCHAR(36)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    host        VARCHAR(255) NOT NULL,
    port        INT          NOT NULL,
    username    VARCHAR(255) NOT NULL,
    password    VARCHAR(255) NOT NULL,
    use_tls     TINYINT(1)   DEFAULT 1,
    use_ssl     TINYINT(1)   DEFAULT 0,
    from_email  VARCHAR(255) NOT NULL,
    is_active   TINYINT(1)   DEFAULT 1,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────── EMAIL QUEUE ─────────────────────────
CREATE TABLE email_queue (
    id              VARCHAR(36)  PRIMARY KEY,
    recipient_email VARCHAR(255) NOT NULL,
    subject         VARCHAR(500) NOT NULL,
    body            LONGTEXT     NOT NULL,
    status          ENUM('PENDING','SENT','FAILED','RETRYING') DEFAULT 'PENDING',
    reference_type  VARCHAR(100),
    reference_id    VARCHAR(36),
    retry_count     INT  DEFAULT 0,
    max_retries     INT  DEFAULT 3,
    sent_at         DATETIME,
    error_message   TEXT,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email_queue_status (status)
);

-- ─────────────────────────────── NOTIFICATIONS ───────────────────────
CREATE TABLE notification_logs (
    id               VARCHAR(36)  PRIMARY KEY,
    recipient_id     VARCHAR(36),
    recipient_email  VARCHAR(255) NOT NULL,
    subject          VARCHAR(500) NOT NULL,
    body             LONGTEXT     NOT NULL,
    notification_type VARCHAR(100) DEFAULT 'EMAIL',
    reference_type   VARCHAR(100),
    reference_id     VARCHAR(36),
    status           VARCHAR(50)  DEFAULT 'PENDING',
    sent_at          DATETIME,
    error_message    TEXT,
    retry_count      INT DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────── AUDIT LOGS ──────────────────────────
CREATE TABLE audit_logs (
    id          VARCHAR(36)  PRIMARY KEY,
    case_id     VARCHAR(36),
    user_id     VARCHAR(36),
    action      VARCHAR(200) NOT NULL,
    entity_type VARCHAR(100),
    entity_id   VARCHAR(36),
    old_value   JSON,
    new_value   JSON,
    ip_address  VARCHAR(50),
    user_agent  VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_case   (case_id),
    INDEX idx_audit_user   (user_id),
    INDEX idx_audit_action (action)
);

-- ─────────────────────────────── MEDICAL ─────────────────────────────
CREATE TABLE medical_requests (
    id           VARCHAR(36) PRIMARY KEY,
    case_id      VARCHAR(36) NOT NULL,
    customer_id  VARCHAR(36) NOT NULL,
    requirements JSON,
    status       VARCHAR(50)  DEFAULT 'PENDING',
    ops_remarks  TEXT,
    reviewed_by  VARCHAR(36),
    reviewed_at  DATETIME,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id),
    INDEX idx_medical_case   (case_id),
    INDEX idx_medical_status (status)
);

CREATE TABLE medical_documents (
    id                 VARCHAR(36)  PRIMARY KEY,
    medical_request_id VARCHAR(36)  NOT NULL,
    customer_id        VARCHAR(36)  NOT NULL,
    document_type      VARCHAR(100) NOT NULL,
    file_name          VARCHAR(500) NOT NULL,
    file_path          VARCHAR(1000) NOT NULL,
    file_size          INT,
    mime_type          VARCHAR(100),
    uploaded_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified           TINYINT(1)   DEFAULT 0,
    verified_by        VARCHAR(36),
    FOREIGN KEY (medical_request_id) REFERENCES medical_requests(id)
);

-- ─────────────────────────────── RAG / KNOWLEDGE ─────────────────────
CREATE TABLE knowledge_documents (
    id           VARCHAR(36)  PRIMARY KEY,
    title        VARCHAR(500) NOT NULL,
    file_name    VARCHAR(500) NOT NULL,
    file_path    VARCHAR(1000) NOT NULL,
    file_type    VARCHAR(50)  NOT NULL,
    file_size    INT,
    status       ENUM('PENDING','PROCESSING','INDEXED','FAILED') DEFAULT 'PENDING',
    chunk_count  INT DEFAULT 0,
    uploaded_by  VARCHAR(36),
    indexed_at   DATETIME,
    error_msg    TEXT,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kb_status (status)
);

-- ─────────────────────────────── CONVERSATIONS ───────────────────────
CREATE TABLE conversation_sessions (
    id            VARCHAR(36)  PRIMARY KEY,
    user_id       VARCHAR(36)  NOT NULL,
    title         VARCHAR(500),
    context_store LONGTEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_conv_user (user_id)
);

CREATE TABLE conversation_messages (
    id               VARCHAR(36) PRIMARY KEY,
    session_id       VARCHAR(36) NOT NULL,
    role             ENUM('user','assistant') NOT NULL,
    content          LONGTEXT NOT NULL,
    retrieved_chunks JSON,
    graph_relations  JSON,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id) ON DELETE CASCADE,
    INDEX idx_conv_msg_session (session_id)
);

-- ─────────────────────────────── INSURER CONFIGS ─────────────────────
CREATE TABLE insurer_configs (
    id           VARCHAR(36)  PRIMARY KEY,
    code         VARCHAR(50)  NOT NULL UNIQUE,
    name         VARCHAR(200) NOT NULL,
    base_url     VARCHAR(500),
    api_key      VARCHAR(500),
    is_mock      TINYINT(1)   DEFAULT 1,
    is_active    TINYINT(1)   DEFAULT 1,
    config_json  JSON,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────── LLM CONFIG ──────────────────────────
CREATE TABLE llm_configs (
    id         VARCHAR(36)  PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    model      VARCHAR(100) NOT NULL,
    base_url   VARCHAR(500) NOT NULL,
    timeout_s  INT          DEFAULT 120,
    max_retry  INT          DEFAULT 3,
    is_active  TINYINT(1)   DEFAULT 1,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────── WORKFLOW LOGS ───────────────────────
CREATE TABLE workflow_stage_logs (
    id          VARCHAR(36)  PRIMARY KEY,
    case_id     VARCHAR(36)  NOT NULL,
    from_stage  VARCHAR(100),
    to_stage    VARCHAR(100) NOT NULL,
    triggered_by VARCHAR(36),
    remarks     TEXT,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(id),
    INDEX idx_wf_log_case (case_id)
);

-- ─────────────────────────────── REFRESH TOKENS ──────────────────────
CREATE TABLE refresh_tokens (
    id         VARCHAR(36)  PRIMARY KEY,
    user_id    VARCHAR(36)  NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    expires_at DATETIME     NOT NULL,
    revoked    TINYINT(1)   DEFAULT 0,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_refresh_user (user_id)
);
