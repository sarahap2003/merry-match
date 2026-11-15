# Merry Match: private Secret Santa web app

A working mobile-friendly Python/Flask web app for private Secret Santa assignments. No install required for participants once deployed.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:8000

## Share it publicly

For a hosted, shared app deploy the folder to a web host that supports Python, persistent disk and SQLite (for example Render with a persistent disk, or a VPS). The included `render.yaml` describes a Render deployment with a persistent disk. Put this folder in a GitHub repository, then in Render choose New > Blueprint and select the repository. Review pricing; persistent disks may require a paid plan. Render will provide a public URL. Set `SECRET_KEY` to a strong random value and `DB_PATH` to a persistent location (the blueprint does both). The app is not hosted merely by downloading it.

## How to use

1. Create an exchange with an optional budget and date.
2. Copy the invitation URL into a group chat.
3. Each participant signs up once, keeps their private link, and enters wishlist details.
4. Organizer adds restrictions (one direction at a time) and draws names.
5. Participants revisit their private URL to see only their assigned recipient and their wishlist.

## Privacy and important notes

* Join links are public to anyone who receives them, and anyone with a person's private URL can access their wishlist and assignment. Send private links individually, not to the group.
* The organizer's secret admin URL grants full event management privileges; keep it safe.
* Organizer sees participant links and can impersonate participants, so this is trust-based and not cryptographically secret from organizers.
* SQLite database must live on persistent storage, or events are lost on re-deployment.
* For larger public deployment use HTTPS, additional abuse prevention, account authentication and rate limiting.
* No email delivery is built in. Share the links manually by text or email.
* A draw requires at least 3 participants. An exact backtracking matcher honors forbidden pairs and finds a valid match if one exists.
