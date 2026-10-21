# פריסה ל-Render

הריפו כולל `render.yaml` (blueprint) ו-`Dockerfile` שבונה את שני הצדדים
לאימג׳ אחד: **שירות web יחיד** שמגיש גם את ה-API וגם את האפליקציה.

## למה שירות אחד ולא שניים

`onrender.com` נמצא ברשימת ה-Public Suffix List, ולכן
`api-xyz.onrender.com` ו-`web-xyz.onrender.com` נחשבים **אתרים שונים**.
עוגיית ה-session מוגדרת `SameSite=Lax`, כך שהדפדפן פשוט לא היה שולח אותה
מהאפליקציה ל-API — ההתחברות הייתה נראית כמצליחה ואז "נשכחת" מיד.
מאותו origin אין בעיה, ואין גם צורך ב-CORS.

## שלבים

### 1. דחיפת הקוד ל-GitHub

```bash
git push origin main
```

### 2. יצירת ה-Blueprint

Render → **New → Blueprint** → בחרו את הריפו → Render מזהה את `render.yaml`
ומציג את השירות + בסיס הנתונים.

### 3. מילוי המשתנים המסומנים `sync: false`

בשלב הראשון עדיין לא ידועה הכתובת, אז אפשר למלא ערך זמני ולעדכן אחרי
הפריסה הראשונה:

| משתנה | ערך |
|---|---|
| `POETRY_PUBLIC_API_URL` | `https://<service>.onrender.com` |
| `POETRY_FRONTEND_URL` | אותה כתובת בדיוק |
| `POETRY_GOOGLE__CLIENT_ID` | מ-Google Cloud Console |
| `POETRY_GOOGLE__CLIENT_SECRET` | מ-Google Cloud Console |
| `POETRY_ADMIN__EMAIL` | אימייל המנהל הראשון |
| `POETRY_ADMIN__PASSWORD` | סיסמה חזקה |

`POETRY_SECURITY__SECRET_KEY` נוצר אוטומטית על ידי Render
(`generateValue: true`) ו-`POETRY_DB__URL` מגיע מבסיס הנתונים.

### 4. עדכון Google OAuth

אחרי שהשירות עלה וידועה הכתובת, ב-Google Cloud Console →
**Authorized redirect URIs** הוסיפו בדיוק:

```
https://<service>.onrender.com/api/auth/google/callback
```

**Authorized JavaScript origins — להשאיר ריק** (הזרימה היא שרת-לשרת).

ודאו ש-`POETRY_PUBLIC_API_URL` מצביע לאותה כתובת, אחרת תתקבל שגיאת
`redirect_uri_mismatch`.

### 5. בדיקה

```bash
curl https://<service>.onrender.com/api/health   # {"status":"ok","env":"production"}
curl https://<service>.onrender.com/api/ready    # {"status":"ok","database":true}
```

ואז פתחו את הכתובת בדפדפן והתחברו.

## מה ה-blueprint מגדיר

- **Postgres 16** מנוהל. Render מחזיר `postgresql://`, ומודול ההגדרות
  ממיר אוטומטית ל-`postgresql+asyncpg://`.
- **`POETRY_RUN_MIGRATIONS=true`** — המיגרציות רצות בעליית השרת.
  (`preDeployCommand` הוא פיצ׳ר בתשלום.) הפעולה אידמפוטנטית, ולכן
  הפעלה חוזרת אינה משכפלת נתונים.
- **`POETRY_SECURITY__COOKIE_SECURE=true`** — Render מסיים את ה-TLS,
  כך שהאפליקציה רואה HTTP ולא הייתה מסמנת את העוגייה כ-Secure.
- **Health check** על `/api/health`.

## עלות ומגבלות

ה-blueprint הנוכחי משתמש **רק במשאבים חינמיים** — אין צורך בכרטיס אשראי.

| רכיב | תוכנית | מגבלה |
|---|---|---|
| Web service | `free` | נרדם אחרי 15 דק׳ חוסר פעילות (~30 שניות להתעוררות); אין דיסק קבוע |
| Postgres | `free` | **נמחק אחרי 90 יום** |

**מה אובד בתוכנית החינמית:**

1. **תמונות מנות לא שורדות הפעלה מחדש.** אין דיסק קבוע, ולכן קבצים שהועלו
   נמחקים בכל restart (כולל התעוררות משינה). המנות יחזרו להציג אימוג׳י.
   הנתונים עצמם — חברים, הזמנות, מטבעות — נשמרים בבסיס הנתונים ולא נפגעים.
2. **בקשה ראשונה אחרי שינה איטית** (~30 שניות).
3. **בסיס הנתונים פג אחרי 90 יום.** גבו לפני כן:
   `pg_dump` מהכתובת החיצונית שמופיעה בדשבורד.

**לשדרוג** (תמונות קבועות, בלי שינה) — ב-`render.yaml`:

```yaml
    plan: starter               # ~$7/חודש
    preDeployCommand: alembic upgrade head
    disk:
      name: media
      mountPath: /app/media
      sizeGB: 1
```

ואז להסיר את `POETRY_RUN_MIGRATIONS` ולהוסיף `POETRY_MEDIA_DIR=/app/media`.
השורות האלה מופיעות כהערה ב-`render.yaml`.

## פריסה מקומית לבדיקה

אותו אימג׳ רץ מקומית:

```bash
docker build -t poetry-hummus .
docker run -p 8000:8000 \
  -e POETRY_DB__URL="postgresql://poet@host.docker.internal:5433/poetry_hummus" \
  -e POETRY_SECURITY__SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e POETRY_ADMIN__EMAIL=admin@hummushameshorer.com \
  -e POETRY_ADMIN__PASSWORD=change-me \
  poetry-hummus
```

## חלופה: Helm / Kubernetes

לפריסה ל-Kubernetes יש צ׳ארט ב-`deploy/helm/poetry-hummus` — ראו
`docs/SETUP.md` סעיף 13. שם הארכיטקטורה היא שני שירותים נפרדים מאחורי
אותו ingress, כך שבעיית העוגייה לא קיימת.
