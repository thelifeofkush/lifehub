# Oracle Always Free deployment and private iPhone access

Status: these are deployment tools, not proof that a cloud VM is running.
The desktop remains the active host until the migration is verified.

## Account and instance

The account owner completes [Oracle signup](https://www.oracle.com/cloud/free/),
identity/payment verification, and any agreements. Do not upgrade to a paid plan
or provision resources without an Always Free eligibility label for this setup.
Use a current Ubuntu LTS image, an eligible free shape, and a boot volume within
the account's free storage allowance in its home region. Prefer a small ARM
instance with enough RAM to build the app when available; the Docker image
supports ARM64 and AMD64. Confirm the displayed price/eligibility before creating
the instance. Free capacity and quotas vary; a paid fallback is not authorized.

Create a dedicated SSH key locally and upload only its public `.pub` value to
the VM. Keep private keys under the Git-ignored `.deploy/` directory. Allow SSH
only from the administrator's current IP while bootstrapping. Do not expose
ports 8000 or 443 publicly; the application will be reached through Tailscale.
Confirm the SSH host fingerprint through Oracle's trusted console before adding
it to known_hosts and transferring any secrets.

Oracle may reclaim idle Always Free instances. Encrypted backups outside the VM
are needed to recover from that event. Do not generate fake workload to bypass
provider idle policies.

## Bootstrap the server

Once SSH access is ready, clone this public repo to `/opt/lifehub`, then run:

```sh
sudo bash /opt/lifehub/ops/bootstrap-ubuntu.sh
sudo tailscale up --hostname=lifehub-cloud
sudo tailscale serve --bg http://127.0.0.1:8000
```

The owner signs into Tailscale and approves the server and HTTPS setup. Use
**Serve**, which is private, rather than Funnel. Note the assigned `.ts.net`
HTTPS origin. Keep the Tailscale identity in persistent host storage. Configure
device key expiry appropriately for the unattended server through the Tailscale
admin console; this needs the account owner's security-setting approval.

## Migrate the existing data once

1. Make a consistent SQLite backup on the desktop. Verify its integrity.
2. Stop the desktop LifeHub container for final cutover so there is only one
   writer/sync host. Preserve its volume and `.env` for rollback.
3. Copy `data/lifehub.db` and `.env` to the verified VM over SSH/SCP. Transfer
   secrets privately, never through Git, command-line arguments, or chat output.
4. On the server, set `.env` ownership to the administrator and mode 600; keep
   `data/` mode 700. Preserve `LIFEHUB_ENCRYPTION_KEY`, Plaid credentials, login,
   and every existing Item/access token. Change only `LIFEHUB_PUBLIC_URL` to
   the assigned Tailscale HTTPS origin.
5. Register `<tailscale-https-origin>/expenses/oauth` in Plaid's allowed redirect
   URIs. The owner completes this security-setting step. Existing bank Items
   should not need to be linked again solely because the server changed.
6. Run `sudo docker compose up -d --build` in `/opt/lifehub`. Verify `/health`,
   authentication, transaction/account counts, saved balance history, and bank
   sync. No local database or secrets should be in the Git checkout history.
7. Install Tailscale on the iPhone, sign into the same private network, and open
   the Tailscale HTTPS URL in Safari. Add it to the Home Screen if desired.
8. Test from cellular with Wi-Fi disabled and the desktop LifeHub container
   stopped. Only then is access independent of the desktop. Keep the desktop
   app stopped after cutover to avoid diverging copies of your records.
9. Stop the desktop `lifehub-tunnel` container after the cloud path is verified.
   It must not remain the production address.

## Maintenance that runs on the VM

```sh
cd /opt/lifehub
sudo bash ops/install-maintenance.sh
sudo systemctl list-timers 'lifehub-*'
```

- Docker and the app start at boot and restart after container process failures.
- Every five minutes, a local health check restarts an unresponsive app.
- Daily, a consistent SQLite snapshot and necessary configuration are packaged
  and encrypted with the app's existing Fernet key. Thirty successful copies
  are retained in `data/backups/`. Earlier backup failures don't trigger pruning.
- Ubuntu unattended security updates run on the host. Reboots, application
  upgrades, and schema changes need a reviewed maintenance action. These scripts
  do not give an AI agent continuous unattended administrative access.
- Failed jobs are recorded in `journalctl -u lifehub-backup -u lifehub-health`.
  No external alert delivery is configured until a destination is provided.

## Off-VM encrypted backups

A local disk backup is not enough if Oracle reclaims the VM. Before calling the
migration complete, configure an off-VM destination and verify a restore.

For OCI Object Storage, create a **private** bucket within the free allowance.
Use a dynamic group matching this VM and a narrow instance-principal policy for
that bucket; the account owner reviews and applies the IAM policy. Install the
official OCI CLI on the VM. Place this root-owned, mode-600 file at
`/etc/lifehub-backup.conf`:

```sh
OCI_BACKUP_BUCKET=your-private-backup-bucket
```

The daily job uploads encrypted archives using the VM's instance principal.
Configure a bucket lifecycle retention rule (for example 30 days) to stay within
the free storage allowance. Verify an uploaded archive can be downloaded and
decrypted into a temporary directory. Keep the Fernet encryption key separately
from both the VM and backup bucket (the original desktop `.env` is one copy).
No plain bank data should be uploaded to a public bucket.

Encrypted archive layout: `lifehub.db` plus `configuration.json`. Use
`cryptography.fernet.Fernet(key).decrypt(archive_bytes)` to obtain the tar archive.
Extract only these two expected files into an empty private directory; verify
SQLite `PRAGMA integrity_check` before restoring with the app stopped.

## Recovery and limits

Free hosting does not guarantee uninterrupted service. Provider reclamation,
account suspension, bank reauthorization, and outages may require the owner's
action. On a replacement VM, restore the encrypted backup and the original
encryption key, rejoin Tailscale, and update the app's URL/Plaid redirect if the
hostname changes. Do not mark deployment complete until off-VM backup restore,
restart recovery, and phone access are verified.

References: [Oracle free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/),
[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
