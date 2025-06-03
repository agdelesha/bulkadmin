/**
 * Модуль для управления кэшированием данных на стороне клиента
 */
const CacheManager = {
    // Ключи для хранения данных в localStorage
    KEYS: {
        CATEGORIES: 'cached_categories',
        ALL_PRODUCTS: 'cached_all_products',
        CATEGORY_PRODUCTS: 'cached_category_products_', // + category_name
        CACHE_DURATION: 'cache_duration', // Длительность кэша в миллисекундах
        LAST_CART_UPDATE: 'last_cart_update' // Время последнего обновления корзины
    },

    // Настройки кэша
    settings: {
        // Время жизни кэша по умолчанию - 5 минут
        cacheDuration: 5 * 60 * 1000,
        // Включено ли кэширование
        enabled: false
    },

    /**
     * Инициализация менеджера кэша
     * @param {Object} options - Настройки кэша
     */
    init(options = {}) {
        // Объединяем настройки по умолчанию с переданными
        this.settings = { ...this.settings, ...options };
        
        // Сохраняем настройки в localStorage
        localStorage.setItem(this.KEYS.CACHE_DURATION, this.settings.cacheDuration);
        
        console.log('CacheManager initialized with settings:', this.settings);
        
        // Проверяем, нужно ли очистить кэш при изменении корзины
        this.setupCartChangeListener();
    },

    /**
     * Настройка слушателя изменений корзины для инвалидации кэша
     */
    setupCartChangeListener() {
        // Слушаем событие изменения корзины
        document.addEventListener('cart:updated', (event) => {
            console.log('Cart updated, invalidating product cache');
            // Обновляем время последнего изменения корзины
            localStorage.setItem(this.KEYS.LAST_CART_UPDATE, Date.now());
            // Очищаем кэш товаров, так как количество в корзине изменилось
            this.clearProductsCache();
        });
    },

    /**
     * Получение категорий с сервера или из кэша
     * @returns {Promise<Array>} - Массив категорий
     */
    async getCategories() {
        // Если кэширование отключено, получаем данные с сервера
        if (!this.settings.enabled) {
            return this.fetchCategoriesFromServer();
        }

        // Проверяем наличие кэша и его актуальность
        const cachedData = this.getCachedData(this.KEYS.CATEGORIES);
        if (cachedData) {
            console.log('Using cached categories');
            return cachedData;
        }

        // Если кэш отсутствует или устарел, получаем данные с сервера
        const categories = await this.fetchCategoriesFromServer();
        return categories;
    },

    /**
     * Получение всех товаров с сервера или из кэша
     * @returns {Promise<Array>} - Массив товаров
     */
    async getAllProducts() {
        // Если кэширование отключено, получаем данные с сервера
        if (!this.settings.enabled) {
            return this.fetchAllProductsFromServer();
        }

        // Проверяем наличие кэша и его актуальность
        const cachedData = this.getCachedData(this.KEYS.ALL_PRODUCTS);
        if (cachedData) {
            console.log('Using cached products');
            return cachedData;
        }

        // Если кэш отсутствует или устарел, получаем данные с сервера
        const products = await this.fetchAllProductsFromServer();
        return products;
    },

    /**
     * Получение товаров по категории с сервера или из кэша
     * @param {string} categoryName - Название категории
     * @returns {Promise<Array>} - Массив товаров в категории
     */
    async getProductsByCategory(categoryName) {
        // Если кэширование отключено, получаем данные с сервера
        if (!this.settings.enabled) {
            return this.fetchProductsByCategoryFromServer(categoryName);
        }

        // Проверяем наличие кэша и его актуальность
        const cacheKey = this.KEYS.CATEGORY_PRODUCTS + categoryName;
        const cachedData = this.getCachedData(cacheKey);
        if (cachedData) {
            console.log(`Using cached products for category ${categoryName}`);
            this.showTemporaryMessage(`Используются кэшированные товары категории "${categoryName}"`, 'info', 1000);
            return cachedData;
        }

        // Если кэш отсутствует или устарел, получаем данные с сервера
        const products = await this.fetchProductsByCategoryFromServer(categoryName);
        return products;
    },

    /**
     * Получение данных из кэша
     * @param {string} key - Ключ для получения данных
     * @returns {Object|null} - Данные из кэша или null, если кэш устарел или отсутствует
     */
    getCachedData(key) {
        try {
            // Получаем данные из localStorage
            const cachedDataString = localStorage.getItem(key);
            if (!cachedDataString) {
                return null;
            }

            // Парсим данные
            const cachedData = JSON.parse(cachedDataString);
            
            // Проверяем время кэширования
            const cacheDuration = parseInt(localStorage.getItem(this.KEYS.CACHE_DURATION)) || this.settings.cacheDuration;
            const now = Date.now();
            
            // Проверяем, не устарел ли кэш
            if (now - cachedData.timestamp > cacheDuration) {
                console.log(`Cache for ${key} expired`);
                return null;
            }
            
            // Проверяем, не изменилась ли корзина после кэширования
            const lastCartUpdate = parseInt(localStorage.getItem(this.KEYS.LAST_CART_UPDATE)) || 0;
            if (lastCartUpdate > cachedData.timestamp && (key.includes('products') || key.includes('PRODUCTS'))) {
                console.log(`Cache for ${key} invalidated due to cart update`);
                return null;
            }
            
            return cachedData.data;
        } catch (error) {
            console.error('Error getting cached data:', error);
            return null;
        }
    },

    /**
     * Сохранение данных в кэш
     * @param {string} key - Ключ для сохранения данных
     * @param {Object} data - Данные для сохранения
     */
    setCachedData(key, data) {
        try {
            // Формируем объект для сохранения
            const cacheData = {
                timestamp: Date.now(),
                data: data
            };
            
            // Сохраняем в localStorage
            localStorage.setItem(key, JSON.stringify(cacheData));
            console.log(`Data cached for ${key}`);
        } catch (error) {
            console.error('Error setting cached data:', error);
        }
    },

    /**
     * Показывает временное сообщение пользователю
     * @param {string} message - Текст сообщения
     * @param {string} type - Тип сообщения (info, success, error)
     * @param {number} duration - Длительность показа в миллисекундах
     */
    showTemporaryMessage(message, type = 'info', duration = 3000) {
        // Используем глобальную функцию из base.html, если она доступна
        if (window.showTemporaryMessage) {
            window.showTemporaryMessage(message, type);
            return;
        }
        
        // Запасной вариант, если глобальная функция недоступна (не должен использоваться)
        console.log('Using fallback showTemporaryMessage in CacheManager - this should not happen');
        
        // Проверяем, есть ли контейнер для сообщений
        let container = document.getElementById('temporary-message-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'temporary-message-container';
            document.body.appendChild(container);
        }
        
        // Создаем элемент сообщения
        const messageElement = document.createElement('div');
        messageElement.className = `temporary-message ${type}`;
        messageElement.textContent = message;
        
        // Добавляем в контейнер
        container.appendChild(messageElement);
        
        // Удаляем через указанное время
        setTimeout(() => {
            if (messageElement.parentNode) {
                messageElement.parentNode.removeChild(messageElement);
            }
        }, duration);
    },

    /**
     * Получение категорий с сервера
     * @returns {Promise<Array>} - Массив категорий
     */
    async fetchCategoriesFromServer() {
        try {
            console.log('Fetching categories from server');
            const response = await fetch('/api/categories');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            // API теперь возвращает напрямую массив категорий
            const categories = await response.json();
            
            // Сохраняем данные в кэш
            this.setCachedData(this.KEYS.CATEGORIES, categories);
            
            // Показываем уведомление об успешном кэшировании
            this.showTemporaryMessage('Категории успешно загружены и кэшированы', 'success', 1500);
            
            return categories;
        } catch (error) {
            console.error('Error fetching categories:', error);
            this.showTemporaryMessage('Ошибка при загрузке категорий', 'error');
            return [];
        }
    },

    /**
     * Получение всех товаров с сервера
     * @returns {Promise<Array>} - Массив товаров
     */
    async fetchAllProductsFromServer() {
        try {
            console.log('Fetching all products from server');
            const response = await fetch('/api/products');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            // API теперь возвращает напрямую массив товаров
            const products = await response.json();
            
            // Сохраняем данные в кэш
            this.setCachedData(this.KEYS.ALL_PRODUCTS, products);
            
            // Показываем уведомление об успешном кэшировании
            this.showTemporaryMessage(`Товары (${products.length} шт.) успешно загружены и кэшированы`, 'success', 1500);
            
            return products;
        } catch (error) {
            console.error('Error fetching products:', error);
            this.showTemporaryMessage('Ошибка при загрузке товаров', 'error');
            return [];
        }
    },
    
    /**
     * Получение товаров по категории с сервера
     * @param {string} categoryName - Название категории
     * @returns {Promise<Array>} - Массив товаров в категории
     */
    async fetchProductsByCategoryFromServer(categoryName) {
        try {
            console.log(`Fetching products for category "${categoryName}" from server`);
            const response = await fetch(`/api/products/category/${encodeURIComponent(categoryName)}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            // API теперь возвращает напрямую массив товаров
            const products = await response.json();
            
            // Сохраняем данные в кэш
            const cacheKey = this.KEYS.CATEGORY_PRODUCTS + categoryName;
            this.setCachedData(cacheKey, products);
            
            // Показываем уведомление об успешном кэшировании
            this.showTemporaryMessage(`Товары категории "${categoryName}" (${products.length} шт.) загружены и кэшированы`, 'success', 1500);
            
            return products;
        } catch (error) {
            console.error('Error fetching products by category:', error);
            this.showTemporaryMessage(`Ошибка при загрузке товаров категории "${categoryName}"`, 'error');
            return [];
        }
    },

    /**
     * Очистка кэша товаров
     */
    clearProductsCache() {
        console.log('Clearing products cache');
        
        // Удаляем кэш всех товаров
        localStorage.removeItem(this.KEYS.ALL_PRODUCTS);
        
        // Удаляем кэш товаров по категориям
        // Перебираем все ключи в localStorage
        let clearedCount = 0;
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            // Если ключ начинается с префикса кэша товаров по категориям
            if (key && key.startsWith(this.KEYS.CATEGORY_PRODUCTS)) {
                localStorage.removeItem(key);
                clearedCount++;
            }
        }
        
        // Не показываем уведомление здесь, так как оно будет показано в другом месте
        // this.showTemporaryMessage(`Товар добавлен в корзину`, 'success');
    },

    /**
     * Полная очистка кэша
     */
    clearAllCache() {
        console.log('Clearing all cache');
        
        // Удаляем кэш категорий
        localStorage.removeItem(this.KEYS.CATEGORIES);
        
        // Очищаем кэш товаров
        this.clearProductsCache();
        
        // Показываем уведомление о полной очистке кэша
        this.showTemporaryMessage('Весь кэш успешно очищен', 'success');
    }
};

// Создаем событие для обновления корзины
const cartUpdatedEvent = new Event('cart:updated');

// Экспортируем модуль
window.CacheManager = CacheManager;
