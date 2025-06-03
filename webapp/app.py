from flask import Flask, render_template, url_for, session, redirect, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
import copy # Понадобится для глубокого копирования
from datetime import datetime
import os
import requests
import json
from werkzeug.utils import secure_filename
from functools import wraps

# --- Constants ---
CART_STATUS = 'Корзина' # Статус для активной корзины

app = Flask(__name__)
app.secret_key = os.urandom(24) # Важно для работы сессий! Для продакшена лучше использовать статичный, сгенерированный ключ.

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///products.db' # Путь к файлу БД
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Отключаем отслеживание изменений
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads', 'products')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max upload size
app.config['TELEGRAM_BOT_TOKEN'] = '7873301434:AAFQEldq6m5COTPnfslyoJEtgNDMhljJ6Wc' # !!! Храните токен безопасно, лучше через переменные окружения для продакшена !!!
db = SQLAlchemy(app) # Инициализируем SQLAlchemy

# --- Admin Authentication ---
# Помещаем здесь, чтобы ADMIN_USERNAME, ADMIN_PASSWORD и admin_required были доступны глобально до их использования

ADMIN_USERNAME = 'admin' # Имя пользователя администратора
ADMIN_PASSWORD = '6476'  # Пароль администратора (!!! ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ НА НАДЕЖНЫЙ !!!)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Пожалуйста, войдите, чтобы получить доступ к этой странице.', 'warning')
            return redirect(url_for('admin_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_products_list'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session.permanent = True 
            flash('Вы успешно вошли!', 'success')
            next_url = request.args.get('next')
            return redirect(next_url or url_for('admin_products_list'))
        else:
            flash('Неверное имя пользователя или пароль.', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Вы успешно вышли.', 'success')
    return redirect(url_for('admin_login'))

# --- End Admin Authentication ---

# Модель для таблицы категорий
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Автоинкрементируемый ID
    name = db.Column(db.String(100), unique=True, nullable=False)
    image_url = db.Column(db.String(200), nullable=True) # Путь к изображению категории (относительно static/)

    def __repr__(self):
        return f'<Category {self.name}>'

# Модель для таблицы продуктов
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    detailed_info = db.Column(db.Text, nullable=True)  # Подробная информация о товаре
    proteins = db.Column(db.Float, nullable=True)  # Белки (г)
    fats = db.Column(db.Float, nullable=True)  # Жиры (г)
    carbs = db.Column(db.Float, nullable=True)  # Углеводы (г)
    image_url = db.Column(db.String(200), nullable=True)
    
    # Связь с категорией
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    category = db.relationship('Category', backref=db.backref('products', lazy='dynamic', cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<Product {self.name}>'


class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.BigInteger, primary_key=True)  # Telegram User ID, BigInteger
    first_name = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150), nullable=True)
    username = db.Column(db.String(100), nullable=True, unique=True)
    phone_number = db.Column(db.String(20), nullable=True)  # Поле для номера телефона
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)
    
    orders = db.relationship('Order', backref='client', lazy='dynamic')

    def __repr__(self):
        return f'<Client {self.id} {self.username or self.first_name}>'

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    client_id = db.Column(db.BigInteger, db.ForeignKey('clients.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Новый') # Статусы: Новый, В обработке, Оплачен, Доставлен, Отменен
    
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Order {self.id} by Client {self.client_id} - Status: {self.status}>'

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.String(50), db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    price_at_purchase = db.Column(db.Float, nullable=False)

    product = db.relationship('Product')

    def __repr__(self):
        return f'<OrderItem {self.id} for Order {self.order_id} - Product {self.product_id} x{self.quantity}>'

def create_tables_and_migrate_data():
    with app.app_context():
        # Проверяем, существует ли столбец phone_number в таблице clients
        try:
            # Проверяем наличие таблицы clients
            inspector = db.inspect(db.engine)
            if 'clients' in inspector.get_table_names():
                # Проверяем наличие столбца phone_number
                columns = inspector.get_columns('clients')
                column_names = [column['name'] for column in columns]
                
                if 'phone_number' not in column_names:
                    print("Adding phone_number column to clients table...")
                    # Добавляем столбец phone_number, используя современный синтаксис
                    with db.engine.connect() as conn:
                        conn.execute(text('ALTER TABLE clients ADD COLUMN phone_number VARCHAR(20)'))
                        conn.commit()
                    print("phone_number column added successfully.")
        except Exception as e:
            print(f"Error checking/adding phone_number column: {e}")
            # Продолжаем выполнение, чтобы создать все таблицы
        
        # Создаем все таблицы, если их нет (включая Category и Product)
        db.create_all()

        # --- Миграция данных --- 
        # Этот блок должен выполниться только один раз, если таблицы пусты
        if not Category.query.first() and not Product.query.first():
            print("Таблицы Category и Product пусты, попытка миграции данных...")
            products_data_to_migrate = {
                # Кулинария
                'kulinar_kotlety_govadina_960g': {'name': 'Котлеты из говядины 960 гр', 'price': 1150, 'description': 'Сочные котлеты из отборной говядины.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},
                'kulinar_kotlety_kuritsa_960g': {'name': 'Котлеты из курицы 960 гр', 'price': 1050, 'description': 'Нежные куриные котлеты.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},
                'kulinar_kotlety_schuka_960g': {'name': 'Котлеты из щуки 960 гр', 'price': 1500, 'description': 'Ароматные котлеты из свежей щуки.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},
                'kulinar_shnitsel_kuritsa_960g': {'name': 'Шницель из курицы 960 гр', 'price': 1300, 'description': 'Хрустящий шницель из куриного филе.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},
                'kulinar_kurinye_frikadelki_1000g': {'name': 'Куриные фрикадельки 1000 гр', 'price': 980, 'description': 'Маленькие куриные фрикадельки, идеальны для супа.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},
                'kulinar_khashbrauny_2500g': {'name': 'Хашбрауны 2500 гр', 'price': 700, 'description': 'Картофельные хашбрауны, отличный гарнир.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},
                'kulinar_krokety_1000g': {'name': 'Крокеты 1000 гр', 'price': 650, 'description': 'Хрустящие крокеты с нежной начинкой.', 'category_name': 'Кулинария', 'image_url': 'images/products/placeholder.jpg'},

                # Пельмени
                'pelmeni_s_baraninoy_1000g': {'name': 'Пельмени с бараниной 1000 гр', 'price': 960, 'description': 'Сочные пельмени с начинкой из баранины.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_govyadinoy_1000g': {'name': 'Пельмени с говядиной 1000 гр', 'price': 710, 'description': 'Классические пельмени с говядиной.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_kuritsey_1000g': {'name': 'Пельмени с курицей 1000 гр', 'price': 680, 'description': 'Легкие пельмени с куриной начинкой.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_telyatinoy_gribami_1000g': {'name': 'Пельмени с телятиной и грибами 1000 гр', 'price': 880, 'description': 'Изысканные пельмени с телятиной и грибами.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_utkoy_1000g': {'name': 'Пельмени с уткой 1000 гр', 'price': 960, 'description': 'Оригинальные пельмени с утиной начинкой.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_schukoy_1000g': {'name': 'Пельмени с щукой 1000 гр', 'price': 920, 'description': 'Необычные пельмени с начинкой из щуки.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_sibirskie_1000g': {'name': 'Пельмени Сибирские 1000 гр', 'price': 680, 'description': 'Традиционные сибирские пельмени.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_so_svininoy_1000g': {'name': 'Пельмени со свининой 1000 гр', 'price': 650, 'description': 'Насыщенные пельмени со свиной начинкой.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_tsvetnye_pelmeshki_1000g': {'name': 'Цветные пельмешки 1000 гр', 'price': 760, 'description': 'Яркие и вкусные цветные пельмешки.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_brynzoy_zelenyu_1000g': {'name': 'Пельмени с брынзой и зеленью 1000 гр', 'price': 980, 'description': 'Ароматные пельмени с брынзой и свежей зеленью.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_suluguni_khalapeno_1000g': {'name': 'Пельмени с сулугуни и халапеньо 1000 гр', 'price': 940, 'description': 'Пикантные пельмени с сыром сулугуни и перцем халапеньо.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},
                'pelmeni_s_ostroy_svininoy_1000g': {'name': 'Пельмени с острой свининой 1000 гр', 'price': 700, 'description': 'Острые пельмени для любителей поярче.', 'category_name': 'Пельмени', 'image_url': 'images/products/placeholder.jpg'},

                # Вареники
                'vareniki_s_kartofelem_gribami_1000g': {'name': 'Вареники с картофелем и грибами 1000 гр', 'price': 450, 'description': 'Классические вареники с картошкой и грибами.', 'category_name': 'Вареники', 'image_url': 'images/products/placeholder.jpg'},
                'vareniki_s_kartofelem_lukom_1000g': {'name': 'Вареники с картофелем и луком 1000 гр', 'price': 450, 'description': 'Домашние вареники с картофелем и жареным луком.', 'category_name': 'Вареники', 'image_url': 'images/products/placeholder.jpg'},
                'vareniki_s_kvashenoy_kapustoy_1000g': {'name': 'Вареники с квашенной капустой 1000 гр', 'price': 450, 'description': 'Пикантные вареники с начинкой из квашеной капусты.', 'category_name': 'Вареники', 'image_url': 'images/products/placeholder.jpg'},
                'vareniki_s_vishney_1000g': {'name': 'Вареники с вишней 1000 гр', 'price': 820, 'description': 'Сладкие вареники с сочной вишней.', 'category_name': 'Вареники', 'image_url': 'images/products/placeholder.jpg'},
                'vareniki_s_tvorogom_1000g': {'name': 'Вареники с творогом 1000 гр', 'price': 600, 'description': 'Нежные вареники с творогом.', 'category_name': 'Вареники', 'image_url': 'images/products/placeholder.jpg'},
            }

            # 1. Собрать уникальные имена категорий и создать их
            category_names = set(data['category_name'] for data in products_data_to_migrate.values())
            categories_map = {}
            for cat_name in category_names:
                category = Category.query.filter_by(name=cat_name).first()
                if not category:
                    category = Category(name=cat_name)
                    db.session.add(category)
                categories_map[cat_name] = category
            
            try:
                db.session.commit() # Сохраняем все новые категории
                print(f"Успешно создано/найдено {len(categories_map)} категорий.")
                # Обновляем ID в categories_map после коммита, чтобы они были доступны
                for cat_name in categories_map:
                    categories_map[cat_name] = Category.query.filter_by(name=cat_name).first()
            except Exception as e:
                db.session.rollback()
                print(f"Ошибка при создании категорий: {e}")
                return # Прерываем миграцию, если категории не созданы

            # 2. Мигрировать продукты, связывая их с категориями
            migrated_products_count = 0
            for product_id, data in products_data_to_migrate.items():
                if not db.session.get(Product, product_id): # Исправлено LegacyAPIWarning
                    category_name = data['category_name']
                    category_obj = categories_map.get(category_name)
                    
                    if not category_obj:
                        print(f"ПРЕДУПРЕЖДЕНИЕ: Категория '{category_name}' не найдена для товара '{data['name']}'. Товар не будет добавлен.")
                        continue

                    new_product = Product(
                        id=product_id,
                        name=data['name'],
                        price=data['price'],
                        description=data.get('description', 'Вкусное блюдо от Бульк'),
                        category_id=category_obj.id, # Используем ID категории
                        image_url=data.get('image_url', default_placeholder_image)
                    )
                    db.session.add(new_product)
                    migrated_products_count += 1
            
            if migrated_products_count > 0:
                try:
                    db.session.commit()
                    print(f"Успешно мигрировано {migrated_products_count} товаров.")
                except Exception as e:
                    db.session.rollback()
                    print(f"Ошибка при миграции товаров: {e}")
            else:
                print("Нет новых товаров для миграции из словаря.")
        else:
            print("Таблицы Category и/или Product не пусты, миграция из словаря не требуется.")
        
        # --- Проверка и создание папки для загрузок, если ее нет ---
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            try:
                os.makedirs(app.config['UPLOAD_FOLDER'])
                print(f"Создана папка для загрузок: {app.config['UPLOAD_FOLDER']}")
            except OSError as e:
                print(f"Ошибка при создании папки {app.config['UPLOAD_FOLDER']}: {e}")
        else:
            print(f"Папка для загрузок уже существует: {app.config['UPLOAD_FOLDER']}")

        print("Проверка таблиц и миграция данных завершены.")

default_placeholder_image = "images/products/placeholder.jpg" # Оставляем, используется как fallback
CART_STATUS = "В корзине" # Статус для активной корзины, используется для поиска текущего заказа пользователя

@app.route('/')
def all_products():
    # Получаем параметр поиска, если он есть
    search_query = request.args.get('search', '').strip()
    
    client_id = session.get('client_id')
    cart_items_map = {}
    if client_id:
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        if active_cart:
            cart_items_map = {item.product_id: item.quantity for item in active_cart.items}

    # Если есть поисковый запрос, фильтруем товары
    if search_query:
        db_products = Product.query.filter(Product.name.ilike(f'%{search_query}%')).all()
    else:
        db_products = Product.query.all()
    
    # Создаем список всех товаров без группировки по категориям
    products_list = []
    
    for product in db_products:
        item_display_data = {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'description': product.description,
            'category': product.category.name,
            'image_url': url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image),
            'quantity_in_cart': cart_items_map.get(product.id, 0)
        }
        products_list.append(item_display_data)
        
    return render_template('all_products.html', products_list=products_list, search_query=search_query)

@app.route('/categories')
def categories_list():
    # Запрашиваем все категории из таблицы Category, упорядоченные по имени
    all_categories = Category.query.order_by(Category.name).all()
    # Теперь all_categories - это список объектов Category
    # Шаблон categories_list.html нужно будет обновить, 
    # чтобы он работал с объектами Category (например, category.name, category.image_url)
    return render_template('categories_list.html', categories=all_categories)

@app.route('/category/<string:category_name>') # Добавил string: для явного указания типа
def products_in_category(category_name):
    client_id = session.get('client_id')
    cart_items_map = {}
    if client_id:
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        if active_cart:
            cart_items_map = {item.product_id: item.quantity for item in active_cart.items}
    
    # Ищем категорию по имени в таблице Category
    category_object = Category.query.filter_by(name=category_name).first()
    
    if not category_object:
        flash(f"Категория '{category_name}' не найдена.", "error")
        return redirect(url_for('all_products')) # Или на страницу со списком категорий

    # Получаем товары для найденной категории
    db_products_in_category = Product.query.filter_by(category_id=category_object.id).order_by(Product.name).all()
    
    processed_items = []
    
    # Изображение категории (если оно есть у объекта Category)
    # Если у категории нет своего image_url, можно использовать плейсхолдер или изображение первого товара
    category_image_url_for_template = default_placeholder_image 
    if category_object.image_url:
        category_image_url_for_template = url_for('static', filename=category_object.image_url) # Оборачиваем в url_for
    elif db_products_in_category and db_products_in_category[0].image_url: # Фоллбэк на изображение первого товара
         category_image_url_for_template = url_for('static', filename=db_products_in_category[0].image_url) # Оборачиваем в url_for
    else:
        category_image_url_for_template = url_for('static', filename=default_placeholder_image) # Явный url_for для плейсхолдера

    for product in db_products_in_category:
        item_display_data = {
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'description': product.description,
            'image_url': url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image),
            'quantity_in_cart': cart_items_map.get(product.id, 0)
        }
        processed_items.append(item_display_data)
        
    return render_template('products_in_category.html', 
                           products=processed_items, 
                           category_name=category_object.name, # Передаем актуальное имя категории
                           category_image_url=category_image_url_for_template,
                           category=category_object) # Передаем весь объект категории для гибкости

@app.route('/product/<string:product_id>')
def product_detail(product_id):
    # Получаем товар из базы данных
    product = db.session.get(Product, product_id)
    if not product:
        flash('Товар не найден', 'error')
        return redirect(url_for('all_products'))
    
    # Получаем количество товара в корзине
    quantity_in_cart = 0
    client_id = session.get('client_id')
    
    if client_id:
        # Для авторизованных пользователей используем корзину из БД
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        if active_cart:
            for item in active_cart.items:
                if item.product_id == product_id:
                    quantity_in_cart = item.quantity
                    break
    else:
        # Для неавторизованных пользователей используем сессионную корзину
        session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
        for item in session_cart['items']:
            if item['product_id'] == product_id:
                quantity_in_cart = item['quantity']
                break
    
    # Добавляем информацию о количестве в корзине к объекту товара
    product.quantity_in_cart = quantity_in_cart
    
    return render_template('product_detail.html', product=product)

# @app.route('/add_to_cart/<product_id>', methods=['POST'])
# def add_to_cart(product_id):
    # product = Product.query.get(product_id) # Получаем продукт из БД по ID
    # if not product:
        # return "Товар не найден", 404

    # cart = session.get('cart', [])
    # found_in_cart = False
    # for item_in_cart in cart:
        # if item_in_cart['id'] == product_id:
            # item_in_cart['quantity'] += 1
            # found_in_cart = True
            # break
    
    # if not found_in_cart:
        # # Используем атрибуты объекта Product
        # cart.append({'id': product_id, 'name': product.name, 'price': product.price, 'quantity': 1})
    
    # session['cart'] = cart
    # # Для отладки можно добавить: print(session['cart'])
    # return redirect(request.referrer or url_for('all_products')) # Возвращаем пользователя на предыдущую страницу

@app.route('/cart')
def view_cart():
    client_id = session.get('client_id')
    cart_display_items = []
    total_price = 0

    if client_id:
        # Для авторизованных пользователей используем корзину из БД
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        if active_cart:
            for item in active_cart.items:  # active_cart.items are OrderItem objects
                product = item.product  # Access the related Product object
                if product: # Should always exist due to ForeignKey constraint
                    image_url_for_template = url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image)
                    cart_display_items.append({
                        'id': product.id, # product_id for consistency with template
                        'name': product.name,
                        'quantity': item.quantity,
                        'price': item.price_at_purchase, # Price per unit at time of purchase
                        # 'subtotal': item.quantity * item.price_at_purchase, # Template calculates this
                        'image_url': image_url_for_template
                    })
            total_price = active_cart.total_amount  # Use the stored total_amount from the Order
    else:
        # Для неавторизованных пользователей используем сессионную корзину
        session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
        
        # Получаем информацию о товарах из БД
        for item in session_cart['items']:
            product = Product.query.get(item['product_id'])
            if product:
                image_url_for_template = url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image)
                cart_display_items.append({
                    'id': product.id,
                    'name': product.name,
                    'quantity': item['quantity'],
                    'price': item['price'],
                    'image_url': image_url_for_template
                })
        
        total_price = session_cart['total_amount']
    
    return render_template('cart.html', 
                           cart_items=cart_display_items, 
                           total_price=total_price)

# @app.route('/decrease_from_card/<product_id>', methods=['POST'])
# def decrease_from_card(product_id):
    # cart = session.get('cart', [])
    # product_found_in_cart = False
    # for item_in_cart in cart:
        # if item_in_cart['id'] == product_id:
            # item_in_cart['quantity'] -= 1
            # if item_in_cart['quantity'] == 0:
                # cart.remove(item_in_cart)
            # product_found_in_cart = True
            # break
    
    # if product_found_in_cart:
        # session['cart'] = cart
    
    # return redirect(request.referrer or url_for('all_products'))

@app.route('/remove_from_cart/<product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', [])
    cart = [item for item in cart if item['id'] != product_id]
    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    # Получаем ID клиента
    client_id = session.get('client_id')
    
    try:
        if client_id:
            # Если используется база данных
            active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
            if active_cart:
                # Удаляем все элементы из корзины
                for item in active_cart.items:
                    db.session.delete(item)
                db.session.commit()
        else:
            # Для неавторизованных пользователей очищаем сессионную корзину
            session['session_cart'] = {'items': [], 'total_amount': 0.0}
        
        # Очищаем старую корзину в сессии (для обратной совместимости)
        session['cart'] = []
        
        return jsonify({'status': 'success', 'message': 'Корзина успешно очищена'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@app.context_processor
def inject_cart_item_count():
    client_id = session.get('client_id')
    item_count = 0
    total_amount = 0
    
    if client_id:
        # Для авторизованных пользователей берем данные из БД
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        if active_cart:
            item_count = sum(item.quantity for item in active_cart.items)
            total_amount = active_cart.total_amount
    else:
        # Для неавторизованных пользователей берем данные из сессии
        session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
        item_count = sum(item['quantity'] for item in session_cart['items'])
        total_amount = session_cart['total_amount']
        
    return dict(cart_item_count=item_count, cart_total_amount=total_amount)

# Запрос номера телефона у пользователя
@app.route('/request_phone')
def request_phone():
    client_id = session.get('client_id')
    
    if client_id:
        # Отправляем запрос на номер телефона
        keyboard = {
            "keyboard": [
                [{
                    "text": "Поделиться номером телефона",
                    "request_contact": True
                }]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        
        message_text = "Для оформления заказа, пожалуйста, поделитесь своим номером телефона. Это необходимо для связи с вами по вопросам доставки."
        try:
            send_telegram_message(client_id, message_text, keyboard)
        except Exception as e:
            print(f"Ошибка при отправке запроса на номер телефона: {e}")
    
    # Перенаправляем на страницу подтверждения заказа
    return redirect(url_for('order_placed'))

# Маршрут для сохранения номера телефона (используется только через API)
@app.route('/api/save_phone', methods=['POST'])
def api_save_phone_number():
    data = request.json
    if not data or 'client_id' not in data or 'phone_number' not in data:
        return jsonify({'status': 'error', 'message': 'Отсутствуют необходимые данные'}), 400
    
    client_id = data['client_id']
    phone_number = data['phone_number']
    
    # Сохраняем номер телефона
    client = Client.query.get(client_id)
    if not client:
        return jsonify({'status': 'error', 'message': 'Клиент не найден'}), 404
    
    client.phone_number = phone_number
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Номер телефона сохранен'})

@app.route('/api/cart/add', methods=['POST'])
def api_add_to_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)  # По умолчанию добавляем 1 товар
    
    if not product_id:
        return jsonify({'status': 'error', 'message': 'Не указан product_id'}), 400
    
    try:
        quantity = int(quantity)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Некорректное количество'}), 400
    
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'status': 'error', 'message': 'Товар не найден'}), 404
    
    client_id = session.get('client_id')
    
    # Если пользователь авторизован, используем корзину из БД
    if client_id:
        # Найти активную корзину (заказ со статусом CART_STATUS) для этого клиента
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        
        if not active_cart:
            # Если активной корзины нет, создаем новую
            active_cart = Order(client_id=client_id, status=CART_STATUS, total_amount=0.0)
            db.session.add(active_cart)
            
        # Проверяем, есть ли уже такой товар в корзине
        order_item = None
        if active_cart.id: # Если корзина уже существует в БД (имеет id)
            order_item = OrderItem.query.filter_by(order_id=active_cart.id, product_id=product_id).first()
        
        if order_item:
            # Товар уже в корзине, обновляем количество
            order_item.quantity += quantity
            if order_item.quantity <= 0:
                db.session.delete(order_item)
                final_quantity = 0
            else:
                final_quantity = order_item.quantity
        else:
            # Товара нет в корзине, добавляем новый OrderItem
            if quantity <= 0: # Для новых товаров количество должно быть положительным
                return jsonify({'status': 'error', 'message': 'Количество для нового товара в корзине должно быть положительным'}), 400
            
            order_item = OrderItem(
                product_id=product_id,
                quantity=quantity,
                price_at_purchase=product.price
            )
            active_cart.items.append(order_item)
            final_quantity = quantity
        
        # Пересчитываем общую стоимость заказа
        total_amount = sum(item.quantity * item.price_at_purchase for item in active_cart.items if item.quantity > 0)
        active_cart.total_amount = round(total_amount, 2)
        
        try:
            db.session.commit()
            
            # Считаем общее количество товаров в корзине
            total_items = sum(item.quantity for item in active_cart.items if item.quantity > 0)
            
            return jsonify({
                'status': 'success',
                'message': f'Товар "{product.name}" добавлен/обновлен в корзине.',
                'cart': {
                    'order_id': active_cart.id,
                    'total_amount': active_cart.total_amount,
                    'total_items': total_items,
                    'status': active_cart.status
                },
                'changed_item': {
                    'product_id': product_id,
                    'new_quantity': final_quantity,
                    'price_per_unit': product.price
                }
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': f'Ошибка при обновлении корзины: {str(e)}'}), 500
    
    else:
        # Для неавторизованных пользователей используем сессионную корзину
        # Инициализируем сессионную корзину, если ее нет
        if 'session_cart' not in session:
            session['session_cart'] = {'items': [], 'total_amount': 0.0}
        
        # Проверяем, есть ли уже такой товар в сессионной корзине
        session_cart = session['session_cart']
        session_item = None
        for item in session_cart['items']:
            if item['product_id'] == product_id:
                session_item = item
                break
                
        if session_item:
            # Товар уже в корзине, обновляем количество
            session_item['quantity'] += quantity
            if session_item['quantity'] <= 0:
                # Удаляем товар из корзины, если количество <= 0
                session_cart['items'] = [item for item in session_cart['items'] if item['product_id'] != product_id]
                final_quantity = 0
            else:
                final_quantity = session_item['quantity']
        elif quantity > 0:
            # Добавляем новый товар в корзину
            session_cart['items'].append({
                'product_id': product_id,
                'quantity': quantity,
                'price': product.price
            })
            final_quantity = quantity
        else:
            # Пытаемся уменьшить количество товара, которого нет в корзине
            return jsonify({'status': 'error', 'message': 'Нельзя уменьшить количество товара, которого нет в корзине'}), 400
            
        # Пересчитываем общую стоимость
        total = 0.0
        for item in session_cart['items']:
            total += item['quantity'] * item['price']
        session_cart['total_amount'] = round(total, 2)
        
        # Сохраняем обновленную корзину в сессии
        session['session_cart'] = session_cart
        
        # Считаем общее количество товаров в корзине
        total_items = sum(item['quantity'] for item in session_cart['items'])
        
        return jsonify({
            'status': 'success',
            'message': f'Товар "{product.name}" добавлен/обновлен в корзине.',
            'cart': {
                'order_id': 'session',
                'total_amount': float(session_cart['total_amount']),
                'total_items': total_items,
                'status': CART_STATUS
            },
            'changed_item': {
                'product_id': product_id,
                'new_quantity': final_quantity,
                'price_per_unit': product.price
            }
        })
    
# Страница подтверждения заказа
@app.route('/order_placed')
def order_placed():
    client_id = session.get('client_id')
    
    # Проверяем, есть ли товары в корзине (сессионной или в БД)
    has_items = False
    if client_id:
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        has_items = active_cart and active_cart.items.count() > 0
    else:
        session_cart = session.get('session_cart', {'items': []})
        has_items = len(session_cart['items']) > 0
    
    # Если в корзине есть товары, но пользователь не авторизован, предлагаем авторизоваться
    if not client_id and has_items:
        # Используем имя бота из памяти
        auth_url = f'https://t.me/bulk_b2b_bot?start=auth'
        
        # Отображаем страницу с предложением авторизоваться
        return render_template('auth_required.html', auth_url=auth_url)
    
    # Если пользователь не авторизован и корзина пуста, перенаправляем на главную
    if not client_id:
        flash('Пожалуйста, войдите в систему, чтобы оформить заказ.', 'warning')
        return redirect(url_for('all_products'))
    
    # Находим активную корзину пользователя
    active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
    
    if not active_cart or not active_cart.items:
        flash('Ваша корзина пуста.', 'warning')
        return redirect(url_for('view_cart'))
    
    # Меняем статус корзины на "Оформлен"
    active_cart.status = "Оформлен"
    db.session.commit()
    
    # Отправляем уведомление администратору
    try:
        send_order_notification_to_admin(active_cart)
    except Exception as e:
        print(f"Ошибка при отправке уведомления: {e}")
    
    # Удаляем корзину из сессии (для старого кода, можно удалить если не используется)
    session.pop('cart', None)
    session.pop('session_cart', None)
    
    # Возвращаем шаблон страницы подтверждения заказа
    return render_template('order_placed.html')


@app.route('/admin/')
@app.route('/admin/products/')
@admin_required # Защищаем этот маршрут
def admin_products_list():
    products = Product.query.join(Category).order_by(Category.name, Product.name).all()
    return render_template('admin_products_list.html', products=products)

@app.route('/admin/product/add', methods=['GET', 'POST'])
@admin_required # Защищаем этот маршрут
def admin_add_product():
    all_categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        product_id = request.form.get('id')
        name = request.form.get('name')
        category_id_str = request.form.get('category_id') # Получаем ID категории
        price_str = request.form.get('price')
        description = request.form.get('description')
        detailed_info = request.form.get('detailed_info')
        proteins_str = request.form.get('proteins')
        fats_str = request.form.get('fats')
        carbs_str = request.form.get('carbs')
        image_file = request.files.get('image_file')
        image_url_to_save = None

        # Данные для возврата в форму в случае ошибки
        product_data_for_form = {
            'id': product_id, 
            'name': name, 
            'category_id': category_id_str, 
            'price': price_str, 
            'description': description,
            'detailed_info': detailed_info,
            'proteins': proteins_str,
            'fats': fats_str,
            'carbs': carbs_str,
            'image_url': None # Будет обновлено если изображение загружено
        }

        if not all([product_id, name, category_id_str, price_str]):
            flash('Ошибка: ID, Название, Категория и Цена являются обязательными полями.', 'error')
            return render_template('admin_product_form.html',
                                   form_title="Добавить новый товар",
                                   form_action=url_for('admin_add_product'),
                                   submit_button_text="Добавить товар",
                                   product=product_data_for_form,
                                   categories=all_categories)
        
        category_obj = None
        if category_id_str:
            try:
                category_id_int = int(category_id_str)
                category_obj = db.session.get(Category, category_id_int)
                if not category_obj:
                    flash('Ошибка: Выбранная категория не существует.', 'error')
            except ValueError:
                flash('Ошибка: Неверный ID категории.', 'error')
        
        if not category_obj: # Если категория не найдена или ID невалидный
            return render_template('admin_product_form.html',
                                   form_title="Добавить новый товар",
                                   form_action=url_for('admin_add_product'),
                                   submit_button_text="Добавить товар",
                                   product=product_data_for_form,
                                   categories=all_categories)

        price = None
        try:
            price = float(price_str)
            if price < 0:
                raise ValueError("Цена не может быть отрицательной.")
            product_data_for_form['price'] = price # Обновляем для возврата в форму, если дальше ошибка
        except ValueError:
            flash('Ошибка: Цена должна быть корректным числом.', 'error')
            return render_template('admin_product_form.html',
                                   form_title="Добавить новый товар",
                                   form_action=url_for('admin_add_product'),
                                   submit_button_text="Добавить товар",
                                   product=product_data_for_form,
                                   categories=all_categories)

        existing_product = db.session.get(Product, product_id)
        if existing_product:
            flash(f"Ошибка: Товар с ID '{product_id}' уже существует.", 'error')
            return render_template('admin_product_form.html',
                                   form_title="Добавить новый товар",
                                   form_action=url_for('admin_add_product'),
                                   submit_button_text="Добавить товар",
                                   product=product_data_for_form,
                                   categories=all_categories)

        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(file_path)
            image_url_to_save = os.path.join('uploads', 'products', filename)
            product_data_for_form['image_url'] = image_url_to_save # Обновляем для возврата

        # Преобразуем строковые значения в числа или None
        proteins = None
        fats = None
        carbs = None
        
        if proteins_str and proteins_str.strip():
            try:
                proteins = float(proteins_str)
            except ValueError:
                pass
                
        if fats_str and fats_str.strip():
            try:
                fats = float(fats_str)
            except ValueError:
                pass
                
        if carbs_str and carbs_str.strip():
            try:
                carbs = float(carbs_str)
            except ValueError:
                pass
        
        new_product = Product(
            id=product_id,
            name=name,
            category_id=category_obj.id, # Используем ID из объекта категории
            price=price,
            description=description,
            detailed_info=detailed_info,
            proteins=proteins,
            fats=fats,
            carbs=carbs,
            image_url=image_url_to_save
        )
        db.session.add(new_product)
        try:
            db.session.commit()
            flash(f"Товар '{name}' успешно добавлен!", 'success')
            return redirect(url_for('admin_products_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении товара: {e}", 'error')
            return render_template('admin_product_form.html',
                                   form_title="Добавить новый товар",
                                   form_action=url_for('admin_add_product'),
                                   submit_button_text="Добавить товар",
                                   product=product_data_for_form,
                                   categories=all_categories)

    # Для GET запроса
    return render_template('admin_product_form.html', 
                           form_title="Добавить новый товар",
                           form_action=url_for('admin_add_product'),
                           submit_button_text="Добавить товар",
                           product=None, 
                           categories=all_categories)


@app.route('/admin/product/edit/<string:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    product_to_edit = db.session.get(Product, product_id)
    if not product_to_edit:
        flash(f"Товар с ID {product_id} не найден.", 'error')
        return redirect(url_for('admin_products_list'))

    all_categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        # Собираем данные из формы для возможного возврата в шаблон
        form_data = {
            'id': product_to_edit.id, # ID не меняется
            'name': request.form.get('name'),
            'category_id': request.form.get('category_id'),
            'price': request.form.get('price'),
            'description': request.form.get('description'),
            'detailed_info': request.form.get('detailed_info'),
            'proteins': request.form.get('proteins'),
            'fats': request.form.get('fats'),
            'carbs': request.form.get('carbs'),
            'image_url': product_to_edit.image_url # Сохраняем текущее изображение, если новое не загружено
        }

        category_id_str = form_data['category_id']

        if not all([form_data['name'], category_id_str, form_data['price']]):
            flash('Ошибка: Название, Категория и Цена являются обязательными полями.', 'error')
            return render_template('admin_product_form.html',
                                   form_title=f"Редактировать товар: {product_to_edit.name}",
                                   form_action=url_for('admin_edit_product', product_id=product_to_edit.id),
                                   submit_button_text="Сохранить изменения",
                                   product=form_data, # Передаем собранные данные
                                   categories=all_categories)
        
        category_obj = None
        if category_id_str:
            try:
                category_id_int = int(category_id_str)
                category_obj = db.session.get(Category, category_id_int)
                if not category_obj:
                    flash('Ошибка: Выбранная категория не существует.', 'error')
            except ValueError:
                flash('Ошибка: Неверный ID категории.', 'error')
        
        if not category_obj: # Если категория не найдена или ID невалидный
            return render_template('admin_product_form.html',
                                   form_title=f"Редактировать товар: {product_to_edit.name}",
                                   form_action=url_for('admin_edit_product', product_id=product_to_edit.id),
                                   submit_button_text="Сохранить изменения",
                                   product=form_data,
                                   categories=all_categories)
        
        price = None
        try:
            price = float(form_data['price'])
            if price < 0:
                raise ValueError("Цена не может быть отрицательной.")
        except ValueError:
            flash('Ошибка: Цена должна быть корректным числом.', 'error')
            return render_template('admin_product_form.html',
                                   form_title=f"Редактировать товар: {product_to_edit.name}",
                                   form_action=url_for('admin_edit_product', product_id=product_to_edit.id),
                                   submit_button_text="Сохранить изменения",
                                   product=form_data,
                                   categories=all_categories)

        # Преобразуем строковые значения в числа или None
        proteins = None
        fats = None
        carbs = None
        
        if form_data['proteins'] and form_data['proteins'].strip():
            try:
                proteins = float(form_data['proteins'])
            except ValueError:
                pass
                
        if form_data['fats'] and form_data['fats'].strip():
            try:
                fats = float(form_data['fats'])
            except ValueError:
                pass
                
        if form_data['carbs'] and form_data['carbs'].strip():
            try:
                carbs = float(form_data['carbs'])
            except ValueError:
                pass
        
        # Обновляем поля товара
        product_to_edit.name = form_data['name']
        product_to_edit.category_id = category_obj.id
        product_to_edit.price = price
        product_to_edit.description = form_data['description']
        product_to_edit.detailed_info = form_data['detailed_info']
        product_to_edit.proteins = proteins
        product_to_edit.fats = fats
        product_to_edit.carbs = carbs
        
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            if product_to_edit.image_url:
                old_image_path = os.path.join(app.static_folder, product_to_edit.image_url)
                if os.path.exists(old_image_path):
                    try:
                        os.remove(old_image_path)
                    except OSError as e:
                        flash(f"Ошибка при удалении старого изображения: {e}", 'warning')
            
            filename = secure_filename(image_file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(file_path)
            product_to_edit.image_url = os.path.join('uploads', 'products', filename)

        try:
            db.session.commit()
            flash(f"Товар '{product_to_edit.name}' успешно обновлен!", 'success')
            return redirect(url_for('admin_products_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении товара: {e}", 'error')
            # В случае ошибки при коммите, возвращаем форму с уже обновленными данными (кроме image_url, если не загружался новый)
            form_data['name'] = product_to_edit.name
            form_data['category_id'] = str(product_to_edit.category_id)
            form_data['price'] = str(product_to_edit.price)
            form_data['description'] = product_to_edit.description
            form_data['image_url'] = product_to_edit.image_url
            return render_template('admin_product_form.html',
                                   form_title=f"Редактировать товар: {product_to_edit.name}",
                                   form_action=url_for('admin_edit_product', product_id=product_to_edit.id),
                                   submit_button_text="Сохранить изменения",
                                   product=form_data,
                                   categories=all_categories)
    
    # Для GET запроса: передаем данные продукта, преобразовав category_id в строку для формы
    product_data_for_get = {
        'id': product_to_edit.id,
        'name': product_to_edit.name,
        'category_id': str(product_to_edit.category_id), # Для предвыбора в select
        'price': product_to_edit.price,
        'description': product_to_edit.description,
        'image_url': product_to_edit.image_url
    }
    return render_template('admin_product_form.html', 
                           form_title=f"Редактировать товар: {product_to_edit.name}", 
                           form_action=url_for('admin_edit_product', product_id=product_to_edit.id),
                           submit_button_text="Сохранить изменения",
                           product=product_data_for_get,
                           categories=all_categories)

@app.route('/admin/product/delete/<string:product_id>', methods=['POST'])
@admin_required # Защищаем этот маршрут
def admin_delete_product(product_id):
    product_to_delete = Product.query.get_or_404(product_id)
    
    # Опционально: удаление файла изображения с сервера
    # if product_to_delete.image_url:
    #     try:
    #         image_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(product_to_delete.image_url))
    #         if os.path.exists(image_path):
    #             os.remove(image_path)
    #     except Exception as e:
    #         flash(f'Ошибка при удалении файла изображения: {str(e)}', 'warning') # Не блокируем удаление товара из-за файла

    try:
        # Опционально: удаление файла изображения, если он есть
        if product_to_delete.image_url:
            try:
                image_path = os.path.join(app.static_folder, product_to_delete.image_url)
                if os.path.exists(image_path):
                    os.remove(image_path)
                    print(f"Изображение {product_to_delete.image_url} удалено.")
            except Exception as e:
                print(f"Ошибка при удалении файла изображения {product_to_delete.image_url}: {e}")
        
        db.session.delete(product_to_delete)
        db.session.commit()
        flash(f"Товар '{product_to_delete.name}' успешно удален.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении товара: {e}", 'error')
    return redirect(url_for('admin_products_list'))

# --- CRUD для Категорий --- 
@app.route('/admin/categories')
@admin_required
def admin_categories_list():
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin_categories_list.html', categories=categories)

@app.route('/admin/category/add', methods=['GET', 'POST'])
@admin_required
def admin_add_category():
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Название категории не может быть пустым.', 'error')
        else:
            existing_category = Category.query.filter_by(name=name).first()
            if existing_category:
                flash(f'Категория с названием "{name}" уже существует.', 'error')
            else:
                new_category = Category(name=name)
                db.session.add(new_category)
                try:
                    db.session.commit()
                    flash(f'Категория "{name}" успешно добавлена.', 'success')
                    return redirect(url_for('admin_categories_list'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'Ошибка при добавлении категории: {e}', 'error')
    return render_template('admin_category_form.html', form_title="Добавить категорию", category=None, form_action=url_for('admin_add_category'))

@app.route('/admin/category/edit/<int:category_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_category(category_id):
    category_to_edit = Category.query.get_or_404(category_id)
    if request.method == 'POST':
        new_name = request.form.get('name')
        if not new_name:
            flash('Название категории не может быть пустым.', 'error')
        elif new_name == category_to_edit.name:
            flash('Изменений не было.', 'info') # Или просто ничего не делать
            return redirect(url_for('admin_categories_list'))
        else:
            existing_category = Category.query.filter(Category.name == new_name, Category.id != category_id).first()
            if existing_category:
                flash(f'Категория с названием "{new_name}" уже существует.', 'error')
            else:
                category_to_edit.name = new_name
                try:
                    db.session.commit()
                    flash(f'Категория успешно переименована в "{new_name}".', 'success')
                    return redirect(url_for('admin_categories_list'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'Ошибка при переименовании категории: {e}', 'error')
    return render_template('admin_category_form.html', form_title="Редактировать категорию", category=category_to_edit, form_action=url_for('admin_edit_category', category_id=category_id))

@app.route('/admin/category/delete/<int:category_id>', methods=['POST'])
@admin_required
def admin_delete_category(category_id):
    category_to_delete = db.session.get(Category, category_id)
    if not category_to_delete:
        flash(f'Категория с ID {category_id} не найдена.', 'error')
        return redirect(url_for('admin_categories_list'))

    if category_to_delete.products.count() > 0: # Исправленная проверка
        flash(f'Нельзя удалить категорию "{category_to_delete.name}", так как в ней есть товары ({category_to_delete.products.count()} шт.). Сначала удалите или переместите товары.', 'error')
    else:
        try:
            db.session.delete(category_to_delete)
            db.session.commit()
            flash(f'Категория "{category_to_delete.name}" успешно удалена.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при удалении категории: {e}', 'error')
    return redirect(url_for('admin_categories_list'))

# --- Конец CRUD для Категорий ---

# --- API для Telegram Web App ---

@app.route('/api/telegram_user_sync', methods=['POST'])
def telegram_user_sync():
    try:
        data = request.json
        if not data or 'id' not in data:
            return jsonify({'status': 'error', 'message': 'Missing user data or user ID'}), 400

        # Получаем данные из JSON с защитой от None
        telegram_id = data.get('id')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        username = data.get('username', '')

        # Проверяем обязательные поля
        if not telegram_id:
            return jsonify({'status': 'error', 'message': 'Invalid or missing telegram_id'}), 400
        if not first_name:
            first_name = 'Unknown' # Устанавливаем значение по умолчанию

        print(f"Processing Telegram user sync: ID={telegram_id}, name={first_name} {last_name}, username={username}")

        # Получаем клиента из базы данных
        client = Client.query.get(telegram_id)

        if client:
            # Клиент найден, обновляем данные, если изменились
            updated = False

            # Безопасное сравнение с защитой от None
            if client.first_name != first_name:
                client.first_name = first_name
                updated = True
            if (client.last_name or '') != last_name:
                client.last_name = last_name
                updated = True
            if (client.username or '') != username:
                client.username = username
                updated = True
            
            if updated:
                try:
                    db.session.commit()
                    session['client_id'] = client.id
                    print(f"Client updated: ID={client.id}")
                    return jsonify({'status': 'success', 'message': 'Client updated', 'client_id': client.id})
                except Exception as e:
                    db.session.rollback()
                    print(f"Error updating client: {str(e)}")
                    return jsonify({'status': 'error', 'message': f'Error updating client: {str(e)}'}), 500
            else:
                session['client_id'] = client.id # Обновляем сессию на случай, если ее не было
                print(f"Client data up-to-date: ID={client.id}")
                return jsonify({'status': 'success', 'message': 'Client data up-to-date', 'client_id': client.id})
        else:
            # Клиент не найден, создаем нового
            new_client = Client(
                id=telegram_id, 
                first_name=first_name, 
                last_name=last_name, 
                username=username
            )
            try:
                db.session.add(new_client)
                db.session.commit()
                session['client_id'] = new_client.id
                print(f"New client created: ID={new_client.id}")
                return jsonify({'status': 'success', 'message': 'Client created', 'client_id': new_client.id}), 201
            except Exception as e:
                db.session.rollback()
                print(f"Error creating client: {str(e)}")
                # Попытка разобраться в ошибке уникальности, если username уже занят
                if 'UNIQUE constraint failed' in str(e) and 'clients.username' in str(e):
                     return jsonify({'status': 'error', 'message': f'Error creating client: Username {username} might already exist for another Telegram ID.'}), 409
                return jsonify({'status': 'error', 'message': f'Error creating client: {str(e)}'}), 500
    except Exception as e:
        print(f"Unexpected error in telegram_user_sync: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Unexpected error: {str(e)}'}), 500

# --- Конец API для Telegram Web App ---

# --- API для Корзины ---

@app.route('/api/cart/unified', methods=['POST'])
def api_cart_unified():
    """
    Объединенный API-эндпоинт для синхронизации пользователя Telegram и добавления товара в корзину.
    Принимает данные пользователя Telegram и информацию о товаре в одном запросе.
    Если пользователь не авторизован, товар добавляется в сессионную корзину.
    """
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'Отсутствуют данные запроса'}), 400
    
    # Извлекаем данные пользователя и товара
    user_data = data.get('user_data')  # Изменено с 'user' на 'user_data'
    product_id = data.get('product_id')  # Получаем product_id напрямую
    
    # Проверяем, какой режим работы с корзиной используется
    if 'get_quantity' in data and data.get('get_quantity'):
        # Режим получения текущего количества товара в корзине
        quantity = 0
        set_quantity = None
        direct_quantity_mode = False
        get_quantity_mode = True
    elif 'set_quantity' in data:
        # Режим установки точного количества
        set_quantity = data.get('set_quantity', 0)
        quantity = 0  # Значение не будет использоваться в этом режиме
        direct_quantity_mode = True
        get_quantity_mode = False
    else:
        # Режим добавления/удаления количества
        quantity = data.get('quantity', 1)  # Получаем quantity напрямую
        set_quantity = None
        direct_quantity_mode = False
        get_quantity_mode = False
    
    # Проверяем наличие данных о товаре
    if not product_id:
        return jsonify({'status': 'error', 'message': 'Отсутствуют данные о товаре'}), 400
        
    # Получаем информацию о товаре из базы данных
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'status': 'error', 'message': 'Товар не найден'}), 404
        
    # Если это режим получения текущего количества товара в корзине
    if get_quantity_mode:
        current_quantity = 0
        client_id = session.get('client_id')
        
        if client_id:
            # Для авторизованных пользователей используем корзину из БД
            active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
            if active_cart:
                for item in active_cart.items:
                    if item.product_id == product_id:
                        current_quantity = item.quantity
                        break
        else:
            # Для неавторизованных пользователей используем сессионную корзину
            session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
            for item in session_cart['items']:
                if item['product_id'] == product_id:
                    current_quantity = item['quantity']
                    break
        
        # Возвращаем текущее количество товара в корзине
        return jsonify({
            'status': 'success', 
            'changed_item': {
                'product_id': product_id,
                'new_quantity': current_quantity,
                'price_per_unit': float(product.price)
            }
        })
        
    # Если данные пользователя отсутствуют, используем сессионную корзину
    if not user_data or not user_data.get('id'):
        # Добавляем товар в сессионную корзину
        session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
        
        # Проверяем, есть ли уже такой товар в сессионной корзине
        session_item = None
        for item in session_cart['items']:
            if item['product_id'] == product_id:
                session_item = item
                break
        
        if direct_quantity_mode:
            # Режим установки точного количества
            if session_item:
                if set_quantity > 0:
                    # Устанавливаем новое количество
                    session_item['quantity'] = set_quantity
                else:
                    # Удаляем товар из корзины, если количество 0
                    session_cart['items'].remove(session_item)
            elif set_quantity > 0:
                # Добавляем новый товар с указанным количеством
                session_cart['items'].append({
                    'product_id': product_id,
                    'quantity': set_quantity,
                    'price': product.price
                })
        else:
            # Режим добавления/удаления количества
            if session_item:
                # Обновляем количество
                session_item['quantity'] += quantity
                # Удаляем товар из корзины, если количество стало меньше или равно 0
                if session_item['quantity'] <= 0:
                    session_cart['items'].remove(session_item)
            else:
                # Добавляем новый товар
                session_cart['items'].append({
                    'product_id': product_id,
                    'quantity': quantity,
                    'price': product.price
                })
        
        # Пересчитываем общую стоимость
        total = 0.0
        for item in session_cart['items']:
            total += item['quantity'] * item['price']
        session_cart['total_amount'] = round(total, 2)
        
        # Сохраняем обновленную корзину в сессии
        session['session_cart'] = session_cart
        
        # Получаем информацию о текущем количестве товара в корзине
        current_quantity = 0
        for item in session_cart['items']:
            if item['product_id'] == product_id:
                current_quantity = item['quantity']
                break
        
        total_items = sum(item['quantity'] for item in session_cart['items'])
        return jsonify({
            'status': 'success',
            'message': 'Товар добавлен в корзину',
            'cart': {
                'total_items': total_items,
                'total_amount': float(session_cart['total_amount'])
            },
            'changed_item': {
                'product_id': product_id,
                'new_quantity': current_quantity,
                'price_per_unit': product.price
            }
        })
    
    # Синхронизируем пользователя Telegram
    client = sync_telegram_user(user_data)
    if not client:
        return jsonify({'status': 'error', 'message': 'Ошибка синхронизации пользователя Telegram'}), 500
    
    # Сохраняем ID клиента в сессии
    session['client_id'] = client.id
    
    # Перемещаем товары из сессионной корзины в корзину пользователя, если они есть
    migrate_session_cart_to_user(client.id)
    
    # Находим или создаем активную корзину пользователя
    active_cart = Order.query.filter_by(client_id=client.id, status=CART_STATUS).first()
    if not active_cart:
        active_cart = Order(client_id=client.id, status=CART_STATUS, total_amount=0.0)
        db.session.add(active_cart)
    
    # Проверяем, есть ли уже такой товар в корзине пользователя
    order_item = OrderItem.query.filter_by(order_id=active_cart.id, product_id=product_id).first() if active_cart.id else None
    
    if direct_quantity_mode:
        # Режим установки точного количества
        if order_item:
            if set_quantity > 0:
                # Устанавливаем новое количество
                order_item.quantity = set_quantity
            else:
                # Удаляем товар из корзины, если количество 0
                db.session.delete(order_item)
        elif set_quantity > 0:
            # Создаем новый элемент заказа с указанным количеством
            order_item = OrderItem(
                product_id=product_id,
                quantity=set_quantity,
                price_at_purchase=product.price
            )
            active_cart.items.append(order_item)
    else:
        # Режим добавления/удаления количества
        if order_item:
            # Обновляем количество
            order_item.quantity += quantity
            # Удаляем товар из корзины, если количество стало меньше или равно 0
            if order_item.quantity <= 0:
                db.session.delete(order_item)
        else:
            # Создаем новый элемент заказа
            order_item = OrderItem(
                product_id=product_id,
                quantity=quantity,
                price_at_purchase=product.price
            )
            active_cart.items.append(order_item)
    
    # Пересчитываем общую стоимость заказа
    total_amount = sum(item.quantity * item.price_at_purchase for item in active_cart.items)
    active_cart.total_amount = total_amount
    
    # Сохраняем изменения
    db.session.commit()
    
    # Получаем общее количество товаров в корзине
    total_items = sum(item.quantity for item in active_cart.items)
    
    return jsonify({
        'status': 'success',
        'message': 'Товар добавлен в корзину',
        'cart': {
            'total_items': total_items,
            'total_amount': float(active_cart.total_amount)
        },
        'changed_item': {
            'product_id': product_id,
            'new_quantity': order_item.quantity if order_item else 0,
            'price_per_unit': product.price
        }
    })

def migrate_session_cart_to_user(client_id):
    """Перемещает товары из сессионной корзины в корзину пользователя"""
    # Проверяем наличие сессионной корзины
    session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
    if not session_cart['items']:
        return
    
    # Находим или создаем активную корзину пользователя
    active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
    if not active_cart:
        active_cart = Order(client_id=client_id, status=CART_STATUS, total_amount=0.0)
        db.session.add(active_cart)
    
    # Перемещаем товары из сессионной корзины в корзину пользователя
    for session_item in session_cart['items']:
        product_id = session_item['product_id']
        quantity = session_item['quantity']
        product = Product.query.get(product_id)
        
        if not product:
            continue
        
        # Проверяем, есть ли уже такой товар в корзине пользователя
        order_item = OrderItem.query.filter_by(order_id=active_cart.id, product_id=product_id).first() if active_cart.id else None
        
        if order_item:
            # Обновляем количество
            order_item.quantity += quantity
        else:
            # Создаем новый элемент заказа
            order_item = OrderItem(
                product_id=product_id,
                quantity=quantity,
                price_at_purchase=product.price
            )
            active_cart.items.append(order_item)
    
    # Пересчитываем общую стоимость заказа
    total_amount = sum(item.quantity * item.price_at_purchase for item in active_cart.items)
    active_cart.total_amount = total_amount
    
    # Сохраняем изменения
    db.session.commit()
    
    # Очищаем сессионную корзину
    session['session_cart'] = {'items': [], 'total_amount': 0.0}

# --- API для получения состояния корзины ---
@app.route('/api/cart/state', methods=['GET'])
def get_cart_state():
    """API эндпоинт для получения текущего состояния корзины"""
    client_id = session.get('client_id')
    
    if not client_id:
        # Если пользователь не авторизован, возвращаем состояние сессионной корзины
        session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
        total_items = sum(item['quantity'] for item in session_cart['items'])
        
        return jsonify({
            'status': 'success',
            'cart': {
                'total_items': total_items,
                'total_amount': float(session_cart['total_amount'])
            }
        })
    
    try:
        # Находим активную корзину пользователя
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        
        if not active_cart:
            # Если корзина не найдена, возвращаем пустое состояние
            return jsonify({
                'status': 'success',
                'cart': {
                    'total_items': 0,
                    'total_amount': 0.0
                }
            })
        
        # Считаем общее количество товаров в корзине
        total_items_in_cart = sum(item.quantity for item in active_cart.items if item.quantity > 0)
        
        # Формируем ответ с информацией о корзине
        return jsonify({
            'status': 'success',
            'cart': {
                'total_items': total_items_in_cart,
                'total_amount': float(active_cart.total_amount)
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Ошибка при получении состояния корзины: {str(e)}'}), 500

# --- API для получения информации о товарах в корзине ---
@app.route('/api/cart/items', methods=['GET'])
def get_cart_items():
    """API эндпоинт для получения информации о товарах в корзине"""
    client_id = session.get('client_id')
    
    if not client_id:
        # Если пользователь не авторизован, возвращаем товары из сессионной корзины
        session_cart = session.get('session_cart', {'items': [], 'total_amount': 0.0})
        cart_items = []
        
        # Получаем информацию о товарах из БД
        for item in session_cart['items']:
            product = Product.query.get(item['product_id'])
            if product:
                cart_items.append({
                    'id': product.id,
                    'name': product.name,
                    'quantity': item['quantity'],
                    'price': item['price'],
                    'image_url': url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image)
                })
        
        return jsonify({
            'status': 'success',
            'cart_items': cart_items
        })
    
    try:
        # Находим активную корзину пользователя
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        
        if not active_cart:
            # Если корзина не найдена, возвращаем пустой список
            return jsonify({
                'status': 'success',
                'cart_items': []
            })
        
        # Формируем список товаров в корзине
        cart_items = []
        for item in active_cart.items:
            if item.quantity > 0:
                cart_items.append({
                    'id': item.product_id,
                    'name': item.product.name,
                    'quantity': item.quantity,
                    'price': item.price_at_purchase,
                    'image_url': url_for('static', filename=item.product.image_url) if item.product.image_url else url_for('static', filename=default_placeholder_image)
                })
        
        return jsonify({
            'status': 'success',
            'cart_items': cart_items
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Ошибка при получении товаров в корзине: {str(e)}'}), 500

# Маршрут для запроса номера телефона через бота
@app.route('/request_phone_via_bot', methods=['POST'])
def request_phone_via_bot():
    data = request.json
    if not data or 'id' not in data:
        return jsonify({'status': 'error', 'message': 'Отсутствуют данные пользователя или ID пользователя'}), 400
    
    user_id = data['id']
    
    # Создаем кнопку для отправки контакта
    reply_markup = {
        "keyboard": [[
            {
                "text": "Поделиться контактом",
                "request_contact": True
            }
        ]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }
    
    # Отправляем сообщение с кнопкой для запроса контакта
    message_text = "Для оформления заказа нам нужен ваш номер телефона. Пожалуйста, нажмите на кнопку ниже, чтобы поделиться своим контактом."
    
    result = send_telegram_message(user_id, message_text, reply_markup)
    
    if result and result.get('ok'):
        return jsonify({'status': 'success', 'message': 'Запрос на номер телефона отправлен'})
    else:
        return jsonify({'status': 'error', 'message': 'Ошибка при отправке запроса на номер телефона'}), 500

# Функция для синхронизации данных пользователя Telegram с базой данных
def sync_telegram_user(user_data):
    """
    Синхронизирует данные пользователя Telegram с базой данных
    
    :param user_data: Словарь с данными пользователя Telegram
    :return: Объект Client или None в случае ошибки
    """
    try:
        # Проверяем, есть ли данные пользователя
        if not user_data or not isinstance(user_data, dict):
            # Если данных нет или они неверного формата, возвращаем None
            return None
        
        # Получаем ID пользователя
        user_id = user_data.get('id')
        if not user_id:
            return None
        
        # Проверяем, есть ли уже такой пользователь в базе данных
        client = Client.query.get(user_id)
        
        if not client:
            # Если пользователя нет, создаем нового
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            username = user_data.get('username', '')
            
            client = Client(
                id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            db.session.add(client)
        else:
            # Если пользователь уже есть, обновляем его данные
            client.first_name = user_data.get('first_name', client.first_name)
            client.last_name = user_data.get('last_name', client.last_name)
            client.username = user_data.get('username', client.username)
        
        # Сохраняем изменения в базе данных
        db.session.commit()
        
        return client
    except Exception as e:
        print(f"Error syncing Telegram user: {e}")
        db.session.rollback()
        return None

# Функция для отправки сообщений через Telegram API
def send_telegram_message(chat_id, text, reply_markup=None):
    """    
    Отправляет сообщение через Telegram API
    
    :param chat_id: ID чата или пользователя
    :param text: Текст сообщения
    :param reply_markup: Опциональные кнопки или клавиатура
    :return: Ответ от API в формате JSON
    """
    bot_token = app.config['TELEGRAM_BOT_TOKEN']
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(api_url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return None

# Функция для отправки уведомлений администратору о новых заказах
def send_order_notification_to_admin(order):
    """
    Отправляет уведомление администратору о новом заказе
    
    :param order: Объект заказа из базы данных
    :return: Результат отправки уведомления
    """
    # ID администратора из памяти
    admin_id = 906888481
    
    # Получаем информацию о клиенте
    client = Client.query.get(order.client_id) if order.client_id else None
    client_info = f"Клиент: {client.name if client else 'Неизвестно'}"
    phone_info = f"Телефон: {client.phone_number if client and client.phone_number else 'Не указан'}"
    
    # Формируем список товаров
    items_text = ""
    total_amount = 0
    
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            item_price = item.price_at_purchase * item.quantity
            items_text += f"- {product.name} x {item.quantity} = {item_price} руб.\n"
            total_amount += item_price
    
    # Формируем текст уведомления
    message = f"""<b>Новый заказ #{order.id}</b>

{client_info}
{phone_info}

<b>Товары:</b>
{items_text}
<b>Итого:</b> {total_amount} руб."""
    
    # Создаем кнопки для принятия/отмены заказа
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "Принять заказ", "callback_data": f"accept_order:{order.id}:{order.client_id}"},
                {"text": "Отменить заказ", "callback_data": f"cancel_order:{order.id}:{order.client_id}"}
            ]
        ]
    }
    
    # Отправляем уведомление администратору
    return send_telegram_message(admin_id, message, reply_markup)

# Обработчик вебхука для получения обновлений от Telegram
# Маршрут для настройки webhook в Telegram
@app.route('/setup_telegram_webhook')
def setup_telegram_webhook():
    bot_token = app.config['TELEGRAM_BOT_TOKEN']
    
    # Получаем публичный URL из параметра запроса 'public_url'
    # Пример использования: /setup_telegram_webhook?public_url=https://your-tunnel-url.loca.lt
    provided_public_url = request.args.get('public_url')

    if not provided_public_url:
        # Попытка получить из конфигурации, если параметр не передан
        provided_public_url = app.config.get('WEBHOOK_BASE_URL')
        if not provided_public_url:
            return ("Ошибка: Не передан параметр 'public_url' (например, ?public_url=https://your-tunnel.loca.lt) "
                    "и WEBHOOK_BASE_URL не настроен в конфигурации."), 400

    if not provided_public_url.startswith('https://'):
        return f"Ошибка: URL вебхука должен быть HTTPS. Получен: {provided_public_url}", 400

    # Убедимся, что URL не содержит лишних слешей в конце, если он будет комбинироваться
    webhook_base_url = provided_public_url.rstrip('/')
    webhook_url = f"{webhook_base_url}/telegram-webhook"
    
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook?url={webhook_url}"
    print(f"Attempting to set webhook to: {webhook_url}") # Логирование
    try:
        response = requests.get(api_url)
        response.raise_for_status() # Проверка на HTTP ошибки
        response_json = response.json()
        if response_json.get('ok'):
            print(f"Telegram webhook successfully set to {webhook_url}")
            return f"Telegram webhook успешно установлен на {webhook_url}", 200
        else:
            error_description = response_json.get('description', 'Неизвестная ошибка Telegram')
            print(f"Error setting webhook: {error_description}")
            return f"Ошибка установки вебхука: {error_description}", 500
    except requests.exceptions.RequestException as e:
        print(f"Network error setting webhook: {e}")
        return f"Ошибка сети при установке вебхука: {e}", 500

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    print("\n\n===== TELEGRAM WEBHOOK CALLED =====\n\n")
    print("Headers:", request.headers)
    
    try:
        data = request.get_json()
        print("Webhook data:", data)
    except Exception as e:
        print("Error parsing JSON:", e)
        data = {}
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400
    
    # Обрабатываем команду /start
    if 'message' in data and 'text' in data['message'] and data['message']['text'] == '/start':
        user_id = data['message']['from']['id']
        first_name = data['message']['from'].get('first_name', '')
        
        # Создаем кнопку для запроса номера телефона
        reply_markup = {
            "keyboard": [[
                {
                    "text": "Поделиться номером телефона",
                    "request_contact": True
                }
            ]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        
        # Отправляем приветственное сообщение с кнопкой
        welcome_message = f"Привет, {first_name}! Добро пожаловать в наш магазин. Чтобы мы могли связаться с вами по вопросам заказа, пожалуйста, поделитесь своим номером телефона."
        send_telegram_message(user_id, welcome_message, reply_markup)
        
        return jsonify({'status': 'ok'})
    
    # Обрабатываем сообщения с контактами (номерами телефонов)
    if 'message' in data and 'contact' in data['message']:
        message = data['message']
        contact = message['contact']
        user_id = message['from']['id']
        phone_number = contact['phone_number']
        
        # Проверяем, есть ли клиент в базе данных
        client = Client.query.get(user_id)
        
        # Если клиент существует, проверяем, изменился ли номер телефона
        if client:
            # Проверяем, если номер телефона уже сохранен и не изменился
            if client.phone_number != phone_number:
                # Сохраняем новый номер телефона
                client.phone_number = phone_number
                db.session.commit()
                
                # Убираем кнопку после получения номера телефона
                remove_keyboard = {
                    "remove_keyboard": True
                }
                
                # Отправляем подтверждение с пустой клавиатурой
                send_telegram_message(user_id, "Спасибо! Ваш номер телефона сохранен.", remove_keyboard)
                
                # Проверяем, есть ли активный заказ
                active_order = Order.query.filter_by(client_id=user_id, status="Оформлен").first()
                if active_order:
                    # Отправляем обновленное уведомление администратору
                    send_order_notification_to_admin(active_order)
            else:
                # Если номер телефона не изменился, просто убираем кнопку
                remove_keyboard = {
                    "remove_keyboard": True
                }
                send_telegram_message(user_id, "Ваш номер телефона уже сохранен в системе.", remove_keyboard)
        
        return jsonify({'status': 'ok'})
    
    # Обрабатываем callback запросы (нажатия на кнопки)
    if 'callback_query' in data:
        callback_query = data['callback_query']
        callback_data = callback_query['data']
        
        # Обрабатываем кнопки принятия/отмены заказа
        if callback_data.startswith('accept_order:'):
            _, order_id, client_id = callback_data.split(':')
            order = Order.query.get(int(order_id))
            
            if order:
                # Меняем статус заказа на "Принят"
                order.status = "Принят"
                db.session.commit()
                
                # Отправляем уведомление клиенту
                client_message = f"<b>Ваш заказ принят!</b>\n\nМы свяжемся с вами в ближайшее время для уточнения деталей доставки."
                send_telegram_message(client_id, client_message)
                
                # Обновляем сообщение, убирая кнопки
                message_id = callback_query.get('message', {}).get('message_id')
                chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
                
                if message_id and chat_id:
                    # Формируем обновленный текст сообщения
                    original_text = callback_query.get('message', {}).get('text', '')
                    updated_text = original_text + f"\n\n✅ Заказ принят ({datetime.now().strftime('%H:%M:%S')})"
                    
                    # Отправляем запрос на редактирование сообщения
                    bot_token = get_telegram_bot_token()
                    edit_message_url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                    edit_data = {
                        'chat_id': chat_id,
                        'message_id': message_id,
                        'text': updated_text,
                        'parse_mode': 'HTML'
                    }
                    requests.post(edit_message_url, json=edit_data)
                
                # Отвечаем на callback запрос
                return jsonify({
                    'method': 'answerCallbackQuery',
                    'callback_query_id': callback_query['id'],
                    'text': f"Заказ #{order_id} принят!"
                })
        
        elif callback_data.startswith('cancel_order:'):
            _, order_id, client_id = callback_data.split(':')
            order = Order.query.get(int(order_id))
            
            if order:
                # Меняем статус заказа на "Отменен"
                order.status = "Отменен"
                db.session.commit()
                
                # Отправляем уведомление клиенту
                client_message = f"<b>Ваш заказ отменен.</b>\n\nПожалуйста, свяжитесь с нами для уточнения причины отмены."
                send_telegram_message(client_id, client_message)
                
                # Обновляем сообщение, убирая кнопки
                message_id = callback_query.get('message', {}).get('message_id')
                chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
                
                if message_id and chat_id:
                    # Формируем обновленный текст сообщения
                    original_text = callback_query.get('message', {}).get('text', '')
                    updated_text = original_text + f"\n\n❌ Заказ отменен ({datetime.now().strftime('%H:%M:%S')})"
                    
                    # Отправляем запрос на редактирование сообщения
                    bot_token = get_telegram_bot_token()
                    edit_message_url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                    edit_data = {
                        'chat_id': chat_id,
                        'message_id': message_id,
                        'text': updated_text,
                        'parse_mode': 'HTML'
                    }
                    requests.post(edit_message_url, json=edit_data)
                
                # Отвечаем на callback запрос
                return jsonify({
                    'method': 'answerCallbackQuery',
                    'callback_query_id': callback_query['id'],
                    'text': f"Заказ #{order_id} отменен."
                })
    
    return jsonify({'status': 'ok'})

# --- API для подсказок поиска ---
@app.route('/api/search_suggestions')
def search_suggestions():
    query = request.args.get('query', '').strip()
    print(f"[SEARCH_SUGGESTIONS] Received search query: '{query}', length: {len(query)}, repr: {repr(query)}")
    suggestions = []
    if query and len(query) >= 2: # Начинаем поиск после ввода 2 символов
        # Ищем товары, название которых содержит введенный запрос (регистронезависимо)
        # Ограничиваем количество подсказок, например, до 10
        products = Product.query.filter(Product.name.ilike(f'%{query}%')).limit(10).all()
        suggestions = [product.name for product in products]
    return jsonify(suggestions)

@app.route('/api/filter_products')
def api_filter_products():
    search_query = request.args.get('search', '').strip()
    print(f"[API_FILTER_PRODUCTS] Received search query: '{search_query}', length: {len(search_query)}, repr: {repr(search_query)}")
    
    client_id = session.get('client_id')
    cart_items_map = {}
    if client_id:
        active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
        if active_cart:
            cart_items_map = {item.product_id: item.quantity for item in active_cart.items}

    if search_query:
        db_products = Product.query.filter(Product.name.ilike(f'%{search_query}%')).all()
    else:
        db_products = Product.query.all()
    
    products_list = []
    for product_db in db_products:
        category_name = product_db.category.name if product_db.category else 'Без категории'
        products_list.append({
            'id': product_db.id,
            'name': product_db.name,
            'price': product_db.price,
            'description': product_db.description,
            'image_url': url_for('static', filename=product_db.image_url) if product_db.image_url else url_for('static', filename=default_placeholder_image),
            'category': category_name,
            'quantity_in_cart': cart_items_map.get(product_db.id, 0)
        })
    
    return render_template('_product_grid_partial.html', products_list=products_list, search_query=search_query)

# --- API для кэширования данных на клиенте ---

@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    """
    API-эндпоинт для получения списка всех категорий в формате JSON
    """
    try:
        # Получаем все категории
        all_categories = Category.query.order_by(Category.name).all()
        
        # Формируем список категорий для ответа
        categories_data = []
        for category in all_categories:
            categories_data.append({
                'id': category.id,
                'name': category.name,
                'image_url': url_for('static', filename=category.image_url) if category.image_url else url_for('static', filename=default_placeholder_image)
            })
        
        # Добавляем временную метку для кэширования
        timestamp = datetime.now().timestamp()
        
        # Возвращаем напрямую массив категорий для упрощения обработки на клиенте
        return jsonify(categories_data)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/products', methods=['GET'])
def api_get_all_products():
    """
    API-эндпоинт для получения всех товаров в формате JSON
    """
    try:
        # Получаем данные о корзине пользователя
        client_id = session.get('client_id')
        cart_items_map = {}
        if client_id:
            active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
            if active_cart:
                cart_items_map = {item.product_id: item.quantity for item in active_cart.items}
        
        # Получаем все товары
        db_products = Product.query.all()
        
        # Формируем список товаров для ответа
        products_data = []
        for product in db_products:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'description': product.description,
                'category_id': product.category_id,
                'category_name': product.category.name,
                'image_url': url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image),
                'quantity_in_cart': cart_items_map.get(product.id, 0)
            })
        
        # Добавляем временную метку для кэширования
        timestamp = datetime.now().timestamp()
        
        # Возвращаем напрямую массив товаров для упрощения обработки на клиенте
        return jsonify(products_data)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/products/category/<string:category_name>', methods=['GET'])
def api_get_products_by_category(category_name):
    """
    API-эндпоинт для получения товаров по категории в формате JSON
    """
    try:
        # Получаем данные о корзине пользователя
        client_id = session.get('client_id')
        cart_items_map = {}
        if client_id:
            active_cart = Order.query.filter_by(client_id=client_id, status=CART_STATUS).first()
            if active_cart:
                cart_items_map = {item.product_id: item.quantity for item in active_cart.items}
        
        # Ищем категорию по имени
        category_object = Category.query.filter_by(name=category_name).first()
        
        if not category_object:
            return jsonify({
                'status': 'error',
                'message': f"Категория '{category_name}' не найдена."
            }), 404
        
        # Получаем товары для найденной категории
        db_products_in_category = Product.query.filter_by(category_id=category_object.id).order_by(Product.name).all()
        
        # Формируем список товаров для ответа
        products_data = []
        for product in db_products_in_category:
            products_data.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'description': product.description,
                'category_id': product.category_id,
                'category_name': product.category.name,
                'image_url': url_for('static', filename=product.image_url) if product.image_url else url_for('static', filename=default_placeholder_image),
                'quantity_in_cart': cart_items_map.get(product.id, 0)
            })
        
        # Добавляем временную метку для кэширования
        timestamp = datetime.now().timestamp()
        
        # Возвращаем напрямую массив товаров для упрощения обработки на клиенте
        return jsonify(products_data)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# --- Конец функций для работы с Telegram API ---

if __name__ == '__main__':
    create_tables_and_migrate_data() # Вызываем функцию создания таблиц и миграции
    app.run(host='0.0.0.0', port=5001, debug=True)