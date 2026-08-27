Clone the Repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git

cd nagri (your project name)

Create Virtual Environment
python -m venv .venv
.venv\Scripts\activate

Install Dependencies
pip install -r requirements.txt

Create Environment Variables
Create a .env file in the project directory.
DJANGO_SECRET_KEY=your-secret-key

DEBUG=true

DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASSWORD=your_database_password
DB_HOST=127.0.0.1
DB_PORT=5432

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

Run Database Migrations
python manage.py makemigrations
python manage.py migrate

Create Superuser
python manage.py createsuperuser

Run Development Server
python manage.py runserver
http://127.0.0.1:8000/

Database Configuration
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE

Deployment
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
.
DJANGO_SECRET_KEY
DEBUG
DATABASE_URL
ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS

Security
.env
database passwords
Django SECRET_KEY
email passwords
API keys

.gitignore
v

backend
![alt text](image.png)

frant
![alt text](image-1.png)
