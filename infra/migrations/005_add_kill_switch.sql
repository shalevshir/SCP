-- Kill Switch State Table
-- Emergency trading halt capability with persistence across restarts

CREATE TABLE IF NOT EXISTS kill_switch_state (
    service_name VARCHAR(50) PRIMARY KEY,
    is_killed BOOLEAN NOT NULL DEFAULT FALSE,
    killed_at TIMESTAMPTZ,
    killed_by VARCHAR(100),
    reason TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default rows for both services
INSERT INTO kill_switch_state (service_name, is_killed)
VALUES ('bot-core', FALSE), ('execution', FALSE)
ON CONFLICT (service_name) DO NOTHING;

-- Auto-update trigger for updated_at
DROP TRIGGER IF EXISTS update_kill_switch_updated_at ON kill_switch_state;
CREATE TRIGGER update_kill_switch_updated_at
    BEFORE UPDATE ON kill_switch_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE kill_switch_state IS 'Emergency kill switch state for trading services';
