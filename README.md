# HeavyLift CRM — Full Deployment Guide

## Project Structure

```
heavylift_crm/
│
├── backend/                  ← ALL Python / server files
│   ├── app.py                ← Flask entry point (run this)
│   ├── config.py             ← Settings & env vars
│   ├── database.py           ← PostgreSQL schema + seeder
│   ├── requirements.txt      ← Python packages
│   ├── .env.example          ← Copy to .env with real values
│   │
│   └── routes/               ← One file per page/module
│       ├── auth.py           ← Login, logout, change password
│       ├── users.py          ← User management (admin/dev only)
│       ├── locations.py      ← Locations CRUD + analytics
│       ├── courses.py        ← Courses CRUD + analytics
│       ├── inquiries.py      ← Inquiry CRUD, follow-up, export
│       ├── followup_list.py  ← Follow-up list page
│       ├── offers.py         ← Offers & discounts
│       ├── whatsapp.py       ← WhatsApp templates
│       ├── reports.py        ← Chart data API
│       └── notifications.py  ← Notification system
│
├── frontend/                 ← ALL HTML / CSS / JS files
│   ├── templates/
│   │   ├── base.html         ← Sidebar layout (shared)
│   │   ├── login.html        ← Animated login page
│   │   ├── dashboard.html    ← Home dashboard
│   │   ├── error.html        ← 404/500 error page
│   │   ├── users/            ← User management pages
│   │   ├── locations/        ← Locations + analytics
│   │   ├── courses/          ← Courses + analytics
│   │   ├── inquiries/        ← Inquiries + follow-up form
│   │   ├── followup/         ← Follow-up list page
│   │   ├── offers/           ← Offers management
│   │   ├── whatsapp/         ← Message templates
│   │   └── reports/          ← Charts dashboard
│   │
│   └── static/
│       ├── css/main.css      ← Full black & yellow stylesheet
│       └── js/main.js        ← All interactivity
│
├── Procfile                  ← For Railway / Render / Heroku
└── README.md                 ← This file
```

---

## Local Setup

Important:
The files in `frontend/templates/` are Jinja templates. Do not open `base.html`, `dashboard.html`, or other template files directly in a browser or with VS Code Live Server, or you will see raw tags like `{% block ... %}` and `{{ ... }}` instead of the real UI.

### 1. PostgreSQL

```sql
-- In psql or pgAdmin:
CREATE DATABASE inquiry_db;
```

### 2. Environment

```bash
cd backend
cp .env.example .env
# Edit .env with your real DB password and secret key
```

### 3. Python

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
flask --app app init-db
flask --app app bootstrap-user
flask --app app security-audit
```

### 4. Run

```bash
python app.py
# Opens at http://127.0.0.1:5000
# Use python app.py instead of flask run so Socket.IO starts correctly
```

Then open:

```text
http://127.0.0.1:5000/login
```

---

## Deploy Online

### Option A — Railway (Recommended, free tier available)

1. Push this repo to GitHub
2. Go to https://railway.app → New Project → Deploy from GitHub
3. Add a **PostgreSQL** plugin inside Railway
4. Set environment variables in Railway dashboard:
   ```
   DB_HOST     = (Railway gives you this)
   DB_PORT     = 5432
   DB_NAME     = railway
   DB_USER     = postgres
   DB_PASS     = (Railway gives you this)
   SECRET_KEY  = any-long-random-string
   DEBUG       = False
   ```
5. Railway auto-detects the `Procfile` and deploys

### Option B — Render (Free tier)

1. Push to GitHub
2. Go to https://render.com → New → Web Service
3. Connect your repo
4. Build command: `pip install -r backend/requirements.txt`
5. Start command: `cd backend && gunicorn app:app --workers 1 --threads 100`
6. Add a **PostgreSQL** database in Render
7. Set the same environment variables

### Option C — Heroku

```bash
heroku create heavylift-crm
heroku addons:create heroku-postgresql:mini
heroku config:set SECRET_KEY=your-secret DEBUG=False
git push heroku main
```

### Option D — VPS (Ubuntu/DigitalOcean)

```bash
# Install dependencies
sudo apt update && sudo apt install python3-pip postgresql nginx -y

# Setup DB
sudo -u postgres createdb inquiry_db
sudo -u postgres psql -c "ALTER USER postgres PASSWORD '<strong-db-password>';"

# Clone & run
git clone <your-repo>
cd heavylift_crm/backend
pip3 install -r requirements.txt
cp .env.example .env && nano .env  # fill in values

# Run with gunicorn
gunicorn app:app --bind 0.0.0.0:5000 --workers 1 --threads 100 --daemon

# Nginx reverse proxy with WebSocket upgrade support
# /etc/nginx/sites-available/heavylift:
# server {
#     listen 443 ssl http2;
#     server_name your-domain.com;
#     ssl_certificate /path/to/fullchain.pem;
#     ssl_certificate_key /path/to/privkey.pem;
#     location / {
#         proxy_pass http://127.0.0.1:5000;
#         proxy_http_version 1.1;
#         proxy_set_header Upgrade $http_upgrade;
#         proxy_set_header Connection "upgrade";
#         proxy_set_header Host $host;
#         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#         proxy_set_header X-Forwarded-Proto https;
#     }
# }
```

---

## Role Permissions

| Action                  | Teacher | Admin | Developer |
|-------------------------|:-------:|:-----:|:---------:|
| View inquiries (own loc)|    ✅   |  ✅   |    ✅     |
| View all inquiries      |    ✗    |  ✅   |    ✅     |
| Add / Edit inquiry      |    ✅   |  ✅   |    ✅     |
| Delete inquiry          |    ✗    |  ✅   |    ✅     |
| Follow-up               |    ✅   |  ✅   |    ✅     |
| Convert to student      |    ✅   |  ✅   |    ✅     |
| Manage locations        |    ✗    |  ✅   |    ✅     |
| Manage courses          |    ✗    |  ✅   |    ✅     |
| Manage offers           |    ✗    |  ✅   |    ✅     |
| WhatsApp templates      |  read   |  ✅   |    ✅     |
| Reports                 |  own    |  ✅   |    ✅     |
| Export Excel            |    ✅   |  ✅   |    ✅     |
| Create user accounts    |    ✗    |  ✅   |    ✅     |
| Change any password     |    ✗    |  ✗    |    ✅     |
| Delete users            |    ✗    |  ✗    |    ✅     |
| Change user roles       |    ✗    |  ✗    |    ✅     |

---

## Key Features

- **Black & Yellow** theme with Roboto font
- **Animated login** page with floating particles
- **Drag-to-reorder** locations and courses
- **Click location/course** → full analytics page
- **Auto follow-up date** set 10 days after inquiry date
- **Notification bell** with real-time badge count
- **Socket.IO notifications** that work locally on `http://127.0.0.1:5000`
- **Optional references** — add up to 3 with + button
- **Offers system** — flat or % discount linked to inquiries
- **WhatsApp direct send** — opens wa.me link with pre-filled message
- **Follow-up list** — tabs: Today / Overdue / Upcoming / All
- **Reports** — 4 live Chart.js charts with date range picker
- **Excel export** with yellow header styling
- **Fully responsive** — works on mobile, tablet, desktop
