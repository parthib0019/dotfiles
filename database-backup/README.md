Kopia Database Backup Setup (Local + Cloud)

  Sequential guide to set up automated database backups to both local disk and cloud storage (S3/B2) using Kopia.
  ──────
  ### Step 1: Install Kopia

  #### Ubuntu / Debian:

    curl -s https://kopia.io/signing-key | sudo gpg --dearmor --yes -o /etc/apt/keyrings/kopia-keyring.gpg
    echo "deb [signed-by=/etc/apt/keyrings/kopia-keyring.gpg] http://packages.kopia.io/apt/ stable main" | sudo tee /etc/apt/sources.list.d/kopia.list
    sudo apt update && sudo apt install -y kopia

  ### Step 2: Initialize Repositories (Local & Cloud)

  Create a secure directory for config files:

    sudo mkdir -p /etc/kopia
    sudo chmod 700 /etc/kopia

  #### 1. Setup Local Repository:

    # Create local repo
    sudo kopia --config-file=/etc/kopia/local.config repository create filesystem --path=/mnt/backups/kopia

    # Set retention policy
    sudo kopia --config-file=/etc/kopia/local.config policy set /var/backups/db --keep-daily 7 --keep-weekly 4 --compression=zstd

  #### 2. Setup Cloud Repository (S3 / B2 / MinIO):

    # Create cloud repo (use 'connect' instead of 'create' if repo already exists)
    sudo kopia --config-file=/etc/kopia/cloud.config repository create s3 \
      --bucket="my-db-backups" \
      --access-key="AWS_ACCESS_KEY" \
      --secret-access-key="AWS_SECRET_KEY" \
      --region="us-east-1"

    # Set retention policy
    sudo kopia --config-file=/etc/kopia/cloud.config policy set /var/backups/db --keep-daily 14 --keep-weekly 8 --compression=zstd
  ──────
  ### Step 3: Create Backup Script

  Create /usr/local/bin/kopia-db-backup.sh:

    #!/bin/bash
    set -euo pipefail

    # Configuration
    BACKUP_DIR="/var/backups/db"
    DB_NAME="rkmvmfamily_local"
    DB_USER="root"
    DB_PASS="abcd"

    export KOPIA_LOCAL_PASS="admin@123"
    export KOPIA_CLOUD_PASS="admin@123"

    LOCAL_CFG="/etc/kopia/local.config"
    CLOUD_CFG="/etc/kopia/cloud.config"

    # 1. Prepare directory & dump database
    mkdir -p "$BACKUP_DIR"
    mysqldump --single-transaction -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" > "$BACKUP_DIR/mydb.sql"

    # 2. Snapshot to Local storage (if configured)
    if [ -f "$LOCAL_CFG" ]; then
        KOPIA_PASSWORD="$KOPIA_LOCAL_PASS" kopia --config-file="$LOCAL_CFG" snapshot create "$BACKUP_DIR"
    fi

    # 3. Snapshot to Cloud storage (if configured)
    if [ -f "$CLOUD_CFG" ]; then
        KOPIA_PASSWORD="$KOPIA_CLOUD_PASS" kopia --config-file="$CLOUD_CFG" snapshot create "$BACKUP_DIR"
    fi

    # 4. Clean local temporary dump file
    rm -f "$BACKUP_DIR"/*

  Make it executable:

    sudo chmod 700 /usr/local/bin/kopia-db-backup.sh
  ──────
  ### Step 4: Automate with Systemd

  #### 1. Service: /etc/systemd/system/kopia-backup.service

    [Unit]
    Description=Kopia Database Backup
    After=network.target mysql.service mariadb.service

    [Service]
    Type=oneshot
    ExecStart=/usr/local/bin/kopia-db-backup.sh

  #### 2. Timer: /etc/systemd/system/kopia-backup.timer

    [Unit]
    Description=Run Kopia Database Backup
    Requires=kopia-backup.service

    [Timer]
    OnCalendar=hourly
    Persistent=true

    [Install]
    WantedBy=timers.target

  #### 3. Enable and start:

    sudo systemctl daemon-reload
    sudo systemctl enable --now kopia-backup.timer
  ──────
  ### Step 5: Verification & Restore

  #### Check status:

    # Run backup manually once:
    sudo systemctl start kopia-backup.service

    # Check logs:
    sudo journalctl -u kopia-backup.service -n 30 --no-pager

    # List snapshots:
    sudo KOPIA_PASSWORD="admin@123" kopia --config-file=/etc/kopia/local.config snapshot list
    sudo KOPIA_PASSWORD="admin@123" kopia --config-file=/etc/kopia/cloud.config snapshot list

  #### Restore a snapshot:

    # 1. Restore the dump file from snapshot ID:
    sudo mkdir -p /tmp/restore
    sudo KOPIA_PASSWORD="admin@123" kopia --config-file=/etc/kopia/local.config snapshot restore <SNAPSHOT_ID> /tmp/restore

    # 2. Import into database:
    mysql -u root -p'abcd' rkmvmfamily_local < /tmp/restore/mydb.sql
    rm -rf /tmp/restore
