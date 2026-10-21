# הקמת הסביבה — Poetry Hummus Club

## 1. Google OAuth

1. פתחו [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials).
2. **Create credentials → OAuth client ID → Web application**.
3. תחת **Authorized redirect URIs** הוסיפו בדיוק:
   - פיתוח: `http://localhost:8000/api/auth/google/callback`
   - ייצור: `https://<your-api-domain>/api/auth/google/callback`
4. תחת **Authorized JavaScript origins**:
   - `http://localhost:5173` (פיתוח), `https://<your-web-domain>` (ייצור)
5. העתיקו את ה-Client ID וה-Client Secret ל-`backend/.env`.

ה-redirect URI נגזר מ-`PUBLIC_API_URL`, לכן ודאו שהוא תואם למה שרשום ב-Google.

## 2. משתני סביבה

```bash
cp backend/.env.example backend/.env
# ערכו: SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BOOTSTRAP_ADMIN_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # ל-SECRET_KEY
```

## 3. הרצה עם Docker (הדרך המהירה)

```bash
docker compose up --build
# web  → http://localhost:5173
# api  → http://localhost:8000/docs
```

## 4. הרצה מקומית לפיתוח

```bash
# Postgres
docker compose up -d db          # מאזין על 5433 כדי לא להתנגש בהתקנה מקומית

# Backend
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
# ב-.env: DATABASE_URL=postgresql+asyncpg://poet:poet@localhost:5433/poetry_hummus
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

## 5. מיגרציות

בפיתוח (`APP_ENV=development`) הטבלאות נוצרות אוטומטית בעליית השרת.
בייצור השתמשו ב-Alembic:

```bash
cd backend
alembic upgrade head                        # החלת מיגרציות
alembic revision --autogenerate -m "..."    # יצירת מיגרציה חדשה
```

## 6. כניסת מנהל

המנהל הראשון נוצר בעליית השרת מתוך `BOOTSTRAP_ADMIN_EMAIL` + `BOOTSTRAP_ADMIN_PASSWORD`.
בדף ההתחברות לחצו **כניסת מנהל מועדון** והזינו את אותם פרטים.

להפיכת חבר קיים למנהל:

```sql
UPDATE users SET role = 'admin' WHERE email = 'someone@example.com';
```

## 7. בדיקות

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

## 8. נתוני דמו

למי שרוצה לראות את לוח הניהול מאוכלס:

```bash
cd backend && .venv/bin/python scripts/seed_demo.py
```

היוצר 6 חברי מועדון עם היסטוריית הזמנות, מטבעות ופעילות. לפיתוח בלבד.

## 9. בעיות נפוצות

- **`pydantic-core` לא מתקמפל** — גרסת Python חדשה מדי. השתמשו ב-3.11–3.13
  (`./setup.sh` בוחר אוטומטית).
- **`BOOTSTRAP_ADMIN_EMAIL` נדחה** — דומיינים כמו `.local` נחשבים שמורים
  ונדחים על ידי ולידציית האימייל. השתמשו בדומיין אמיתי.
- **`redirect_uri_mismatch` מגוגל** — ה-URI ב-Google Console חייב להיות זהה
  ל-`{PUBLIC_API_URL}/api/auth/google/callback`.
