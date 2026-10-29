# Hosting on an Oracle VM with Neo4j Aura and a Cloudflare Tunnel

How to run Mr. Healthcare publicly at an address such as `https://medical.hamzaaziz.dev` (D-032). The API and the page run on an Oracle Cloud Always Free VM (`VM.Standard.E2.1.Micro`: AMD, 1 GB of memory). The graph lives on Neo4j AuraDB Free, because Neo4j alone needs about 1 GB. Visitors reach the site only through a Cloudflare Tunnel, which connects out from the VM, so no application port is open to the internet. The language model reads questions through the stack's own Ollama, signed in to your free Ollama account, at most 6 calls a minute for everyone together (D-033); set `LLM_UNDERSTANDING=off` in `.env` to switch it off. Anyone may ask questions without signing in.

Do the steps in order. Public access is switched on last, after the checks.

## What you need

- An Oracle Cloud account with an Always Free tenancy.
- A Neo4j Aura account.
- An Ollama account (the free plan) for the language model (D-033).
- `hamzaaziz.dev` on Cloudflare (it is) and access to Cloudflare Zero Trust (free).
- A release that contains `compose.hosted.yaml` among its assets.

Secrets (the Aura password and the tunnel token) go only into the VM's `.env`. Never commit them, paste them into an issue or a chat, or put them on a command line.

## 1. Create the resources

1. **VM.** In Oracle Cloud, create a compute instance with the shape `VM.Standard.E2.1.Micro` and the image Canonical Ubuntu 24.04 (x86_64). Add your SSH public key and keep the public IP address. In the subnet's security list, allow TCP 22 only from your own address and nothing else inbound.
2. **Graph.** In the Aura console, create an AuraDB Free instance. Save the credentials file it offers: the connection URI (`neo4j+s://<id>.databases.neo4j.io`), the user (`neo4j`) and the password.
3. **Tunnel.** In Cloudflare Zero Trust, go to Networks, Tunnels, and create a tunnel of type Cloudflared named `medical-chatbot`. Choose Docker as the environment and copy only the token from the command it shows. Do not add a public hostname yet.

## 2. Prepare the VM

Connect with `ssh ubuntu@<public IP>`, then:

```
sudo apt-get update && sudo apt-get -y upgrade
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Install Docker Engine and its Compose plugin from Docker's repository:

```
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker ubuntu
```

Sign out and back in, then check that `docker compose version` reports 2.23.1 or newer (the hosted compose uses inline configs).

Clone the repository and write the settings:

```
git clone https://github.com/hamza-aziz-ai/Medical-ChatBot.git && cd Medical-ChatBot
nano .env && chmod 600 .env
```

`.env` holds:

```
NEO4J_URI=neo4j+s://<id>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<the Aura password>
NEO4J_DATABASE=neo4j
PUBLIC_ORIGIN=https://medical.hamzaaziz.dev
TUNNEL_TOKEN=<the tunnel token>
```

## 3. Deploy a release with public access closed

Download the latest release's hosted assets and use its image digests:

```
TAG=$(curl -fsS https://api.github.com/repos/hamza-aziz-ai/Medical-ChatBot/releases/latest | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])')
mkdir -p deploy/first && for f in compose.hosted.yaml release.env manifest.json; do curl -fsSL -o deploy/first/$f https://github.com/hamza-aziz-ai/Medical-ChatBot/releases/download/$TAG/$f; done
set -a; . deploy/first/release.env; set +a
hosted() { docker compose -f deploy/first/compose.hosted.yaml --project-directory . --env-file .env "$@"; }
```

Before the first import, take an on-demand snapshot in the Aura console if the instance holds anything. The importer replaces this dedicated graph, which belongs to the importer alone: never edit it by hand and never point tests at it.

```
hosted --profile init run --rm importer
hosted up -d ollama api web
hosted exec ollama ollama signin
curl -s http://127.0.0.1:8080/api/health
curl -s 'http://127.0.0.1:8080/api/?search=what+causes+asthma'
```

`ollama signin` prints a link: open it in your browser, signed in to ollama.com, and connect the device; the VM then uses your free plan. Remove the device on ollama.com to cut it off. The health check answers `{"status": "ok"}` and the question gets an answer. cloudflared is not running yet, so nothing is public.

## 4. Measure and check before opening

1. Record memory at rest: `free -m` and `docker stats --no-stream`.
2. Work through the Lane-B pre-ship checklist in [docs/TESTING.md](../../docs/TESTING.md).
3. Enrol the stack for automatic updates and start the timer:

   ```
   python3 scripts/update_stack.py --enroll --hosted
   sudo cp hosting/oracle/medical-chatbot-update.service hosting/oracle/medical-chatbot-update.timer /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now medical-chatbot-update.timer
   ```

4. When the next release arrives, watch `free -m` during its update (pull, then import) and record the peak and the swap used in [docs/TESTING.md](../../docs/TESTING.md).

## 5. Configure Cloudflare, then open

Set the edge policies first:

1. **SSL/TLS, Edge Certificates:** turn on Always Use HTTPS, and enable HSTS (6 months; leave "include subdomains" and preload off unless every subdomain of `hamzaaziz.dev` is HTTPS-only).
2. **Caching, Cache Rules:** create a rule for hostname `medical.hamzaaziz.dev` and URI path starting with `/api/` that bypasses the cache. The API already sends `Cache-Control: no-store`; the rule keeps any other zone setting from overriding it.
3. **Optional, Security, WAF, Rate limiting rules:** the free plan allows one rule, for example blocking a visitor for 10 seconds after 100 requests to `/api/` within 10 seconds.
4. **Maintenance page (D-035).** In Workers & Pages, create a Worker named `medical-chatbot-maintenance` from the Hello World template, replace its code with [hosting/cloudflare/maintenance.js](../cloudflare/maintenance.js) and deploy it. Before adding any route, turn Observability (Workers Logs) off in its settings: with logs on, every request it handles is recorded with its URL. Then, under the zone's Workers Routes, first add the route `medical.hamzaaziz.dev/api/*` with the Worker "None", so questions never pass through it, and only then the route `medical.hamzaaziz.dev/*` for that Worker with the failure mode "Fail open". Do not use "Add Domain": a custom domain makes the Worker the whole site instead of the tunnel. While an update has the tunnel closed, or the VM is down, visitors then see the site's own "being updated" page (503, reloading every 30 s) instead of Cloudflare's error page. To remove it, delete the two routes.

Then open:

```
hosted up -d cloudflared
```

In the tunnel's settings, add the public hostname `medical.hamzaaziz.dev` with the service `HTTP` and the URL `web:8080`. Check from your own machine:

```
curl -sI https://medical.hamzaaziz.dev/
curl -s https://medical.hamzaaziz.dev/api/health
curl -sI 'https://medical.hamzaaziz.dev/api/?search=what+causes+asthma' | grep -i 'cache-control\|cf-cache-status'
```

Expect a 200 page with `Cache-Control: no-cache` (D-037), `{"status": "ok"}`, `Cache-Control: no-store` on the answer, and `cf-cache-status: DYNAMIC` or `BYPASS`. If a public check fails, fix the Cloudflare side; it is never a reason to re-import the graph.

## Running it

- **Updates.** Every 15 minutes the timer runs the updater. For a newer release it checks that the site is healthy, pulls the images, closes public access, rebuilds the graph, checks the page, a question and `/api/health` on the VM, and reopens. If anything fails, it rebuilds the previous release's graph and reopens on that. If that fails too, public access stays closed and the updater stops until you act ([docs/ROLLBACK.md](../../docs/ROLLBACK.md)). A release that changes `compose.hosted.yaml` is not deployed automatically: review it, redeploy it as in step 3 and enrol again.
- **Logs.** `journalctl -u medical-chatbot-update` and `logs/<year>/<Month>/update_stack.log`. cloudflared keeps no logs, because its error messages can contain questions. To debug the tunnel, run it once in the foreground with `hosted run --rm cloudflared tunnel --no-autoupdate run`, then delete what you saw.
- **Aura pauses.** AuraDB Free pauses after 72 hours without use, and the API's 30-second health check counts as use. While it is paused the site answers 503 "The knowledge graph is unavailable" and updates wait; resume it in the Aura console. An instance paused for more than 30 days is deleted; then create a new one, update `.env` and import again.
- **Oracle reclamation.** Oracle may reclaim Always Free instances that stay idle. Upgrading the account to Pay As You Go keeps Always Free resources free; check Oracle's current terms before relying on it.
- **Closing the site.** `hosted stop cloudflared` closes public access at once; `sudo systemctl disable --now medical-chatbot-update.timer` stops updates.
