# הקמת הסביבה — Poetry Hummus Club

## 1. Google OAuth

1. פתחו [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials).
2. **Create credentials → OAuth client ID → Web application**.
3. תחת **Authorized redirect URIs** הוסיפו בדיוק:
   - פיתוח: `http://localhost:8000/api/auth/google/callback`
   - ייצור: `https://<your-api-domain>/api/auth/google/callback`
4. **Authorized JavaScript origins — השאירו ריק.** האפליקציה לא טוענת את ספריית
   ה-JS של גוגל; כל ה-OAuth עובר שרת-לשרת. (גוגל גם דוחה ערך עם `/` בסוף,
   עם השגיאה `Invalid Origin: URIs must not contain a path or end with "/"`.)
5. העתיקו את ה-Client ID וה-Client Secret ל-`backend/.env` והפעילו מחדש את ה-API.

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

## 10. תמונות למנות

מנהל יכול להעלות תמונה לכל מנה מלשונית **תפריט** — לחיצה על הריבוע של המנה פותחת
בחירת קובץ. התמונות נשמרות ב-`backend/media/` ומוגשות תחת `/media`.

- פורמטים נתמכים: JPEG, PNG, GIF, WebP. עד 4MB.
- הזיהוי נעשה לפי תוכן הקובץ ולא לפי הסיומת; SVG נדחה בכוונה (יכול להכיל סקריפט).
- החלפה או הסרה של תמונה מוחקת את הקובץ הישן מהדיסק.
- התיקייה `backend/media/` אינה נכנסת ל-git. בפריסה אמיתית כדאי להעביר את
  האחסון ל-S3 או לעגן volume קבוע, אחרת התמונות ייעלמו בכל פריסה מחדש.

**מחיקת מנה:** מנה שמעולם לא הוזמנה נמחקת לגמרי. מנה שכבר מופיעה בהזמנות עבר
מוסתרת מהתפריט במקום להימחק, כדי לא לשבור את היסטוריית ההזמנות.

## 11. סדר התצוגה של התפריט

בלשונית **תפריט** יש חיצי ▲▼ בשני מקומות:

- **ליד שם הקטגוריה** — מזיז את כל הקבוצה למעלה או למטה. כך למשל אפשר להוריד
  את **קינוחים** לסוף התפריט.
- **בתחילת כל שורה** — מזיז מנה בתוך הקטגוריה שלה.

השינוי נשמר מיד ומשתקף גם אצל הלקוחות. הסדר נשמר בבסיס הנתונים
(`menu_categories.sort_order` ו-`menu_items.sort_order`) ולא בקוד.

מנה שהקטגוריה שלה אינה מוגדרת בטבלת הקטגוריות תוצג בסוף, ולא תיעלם.

## 12. קונפיגורציה וגישה לבסיס הנתונים

ההגדרות מרוכזות ב-`backend/app/configuration/main.py` ומחולקות לקבוצות:
`database`, `security`, `google`, `loyalty`, `admin`.

כל שדה נקרא ממשתנה סביבה בתבנית `POETRY_<קבוצה>__<שדה>`, למשל:

```bash
POETRY_DB__URL=postgresql+asyncpg://poet:pw@db:5432/poetry_hummus
POETRY_DB__POOL_SIZE=15
POETRY_SECURITY__SECRET_KEY=...
POETRY_GOOGLE__CLIENT_ID=...
```

השמות הישנים (`DATABASE_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`…) ממשיכים לעבוד
כ-aliases, כך ש-`.env` קיים לא נשבר.

סודות מוגדרים כ-`SecretStr` ולכן אינם נחשפים בלוגים. בעליית השרת נרשמת כתובת
בסיס הנתונים עם סיסמה ממוסכת (`database.safe_url`).

**גישה לבסיס הנתונים** עוברת כולה דרך `get_db_handler()` ב-`app/db.py`:

- ב-FastAPI: `db: AsyncSession = Depends(get_db)`
- בסקריפטים: `async with get_db_handler().session() as db:`
- בבדיקות: `set_db_handler(...)` מחליף את ה-handler בבסיס נתונים זמני

ה-engine נבנה בעצלתיים, כך שייבוא המודול לעולם לא פותח חיבור.

## 13. פריסה ל-Kubernetes (Helm)

```bash
# יצירת הסוד פעם אחת, מחוץ ל-Helm
kubectl create secret generic poetry-hummus-secrets \
  --from-literal=SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')" \
  --from-literal=DATABASE_PASSWORD='...' \
  --from-literal=GOOGLE_CLIENT_ID='...' \
  --from-literal=GOOGLE_CLIENT_SECRET='...' \
  --from-literal=BOOTSTRAP_ADMIN_EMAIL='admin@hummushameshorer.com' \
  --from-literal=BOOTSTRAP_ADMIN_PASSWORD='...'

helm upgrade --install club deploy/helm/poetry-hummus \
  -f deploy/helm/poetry-hummus/values-prod.yaml \
  --namespace poetry-hummus --create-namespace
```

הצ׳ארט כולל: deployments ל-API ול-web, services, ingress עם TLS,
PVC לתמונות המנות, ו-Job מסוג `pre-upgrade` שמריץ `alembic upgrade head`
לפני שה-pods החדשים עולים.

- `secrets.existingSecret` — מומלץ בייצור; הסודות נקראים לפי מפתח ואינם
  נכתבים ל-release.
- `secrets.values` — נוחות לסביבות בדיקה בלבד (נשמר ב-manifest).
- `/api/ready` מחזיר 503 כשבסיס הנתונים אינו זמין, ומשמש כ-readiness probe.
- אחסון התמונות דורש `ReadWriteMany`. עם storage class מסוג `ReadWriteOnce`
  יש להגביל ל-replica אחת או לעבור ל-S3.
