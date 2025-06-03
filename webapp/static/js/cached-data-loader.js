/**
 * Модуль для загрузки данных с использованием кэша
 */
const CachedDataLoader = {
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
        console.log('Using fallback showTemporaryMessage - this should not happen');
        
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
     * Создает HTML для кнопок добавления в корзину
     * @param {Object} product - Данные о товаре
     * @returns {string} HTML-код для кнопок
     */
    createCartControlsHtml(product) {
        const hasInCart = product.quantity_in_cart > 0;
        
        return `
        <div class="add-to-cart-controls" data-product-id="${product.id}">
            <button type="button" class="add-to-cart-btn js-add-to-cart ${hasInCart ? 'hidden' : ''}" data-product-id="${product.id}">В корзину</button>
            <div class="quantity-controls js-quantity-controls ${!hasInCart ? 'hidden' : ''}">
                <button type="button" class="cart-control-btn minus-btn js-decrease-quantity" data-product-id="${product.id}">-</button>
                <span class="item-in-cart-indicator js-product-quantity-display" data-product-id="${product.id}">${hasInCart ? product.quantity_in_cart : 0}</span>
                <button type="button" class="cart-control-btn plus-btn js-increase-quantity" data-product-id="${product.id}">+</button>
            </div>
        </div>`;
    },
    /**
     * Загрузка и отображение категорий с использованием кэша
     * @param {string} containerId - ID контейнера для отображения категорий
     */
    async loadCategories(containerId = 'categories-container') {
        console.log('Loading categories with cache...');
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container with id ${containerId} not found`);
            this.showTemporaryMessage('Ошибка: контейнер для категорий не найден', 'error');
            return;
        }

        try {
            // Показываем индикатор загрузки
            container.innerHTML = '<div class="loading">Загрузка категорий...</div>';
            
            // Получаем категории из кэша или с сервера
            const categories = await CacheManager.getCategories();
            
            // Если категорий нет, показываем сообщение
            if (!categories || !Array.isArray(categories) || categories.length === 0) {
                container.innerHTML = '<div class="empty-message">Категории не найдены</div>';
                this.showTemporaryMessage('Категории не найдены', 'info');
                return;
            }
            
            // Проверяем, что данные имеют ожидаемую структуру
            if (!categories.every(cat => cat && typeof cat === 'object' && 'name' in cat)) {
                console.error('Invalid categories data structure:', categories);
                container.innerHTML = '<div class="error-message">Ошибка: неверный формат данных категорий</div>';
                this.showTemporaryMessage('Ошибка: неверный формат данных категорий', 'error');
                return;
            }
            
            // Формируем HTML для категорий
            let html = '<div class="categories-grid">';
            categories.forEach(category => {
                html += `
                <div class="category-card">
                    <a href="/category/${encodeURIComponent(category.name)}">
                        <div class="category-image">
                            <img src="${category.image_url || '/static/images/no-image.svg'}" alt="${category.name}" loading="lazy" onerror="this.src='/static/images/no-image.svg'">
                        </div>
                        <div class="category-name">${category.name}</div>
                    </a>
                </div>`;
            });
            html += '</div>';
            
            // Отображаем категории
            container.innerHTML = html;
            
            // Показываем уведомление об успешной загрузке
            if (categories.length > 0) {
                this.showTemporaryMessage(`Загружено ${categories.length} категорий`, 'success', 2000);
            }
            
        } catch (error) {
            console.error('Error loading categories:', error);
            container.innerHTML = '<div class="error-message">Ошибка при загрузке категорий</div>';
            this.showTemporaryMessage('Ошибка при загрузке категорий: ' + error.message, 'error');
        }
    },

    /**
     * Загрузка и отображение всех товаров с использованием кэша
     * @param {string} containerId - ID контейнера для отображения товаров
     */
    async loadAllProducts(containerId = 'products-container') {
        console.log('Loading all products with cache...');
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container with id ${containerId} not found`);
            this.showTemporaryMessage('Ошибка: контейнер для товаров не найден', 'error');
            return;
        }

        try {
            // Показываем индикатор загрузки
            container.innerHTML = '<div class="loading">Загрузка товаров...</div>';
            
            // Получаем товары из кэша или с сервера
            const products = await CacheManager.getAllProducts();
            
            // Если товаров нет, показываем сообщение
            if (!products || !Array.isArray(products) || products.length === 0) {
                container.innerHTML = '<div class="empty-message">Товары не найдены</div>';
                this.showTemporaryMessage('Товары не найдены', 'info');
                return;
            }
            
            // Проверяем, что данные имеют ожидаемую структуру
            if (!products.every(prod => prod && typeof prod === 'object' && 'id' in prod && 'name' in prod)) {
                console.error('Invalid products data structure:', products);
                container.innerHTML = '<div class="error-message">Ошибка: неверный формат данных товаров</div>';
                this.showTemporaryMessage('Ошибка: неверный формат данных товаров', 'error');
                return;
            }
            
            // Группируем товары по категориям
            const productsByCategory = {};
            products.forEach(product => {
                const categoryName = product.category_name || 'Без категории';
                if (!productsByCategory[categoryName]) {
                    productsByCategory[categoryName] = [];
                }
                productsByCategory[categoryName].push(product);
            });
            
            // Формируем HTML для товаров, сгруппированных по категориям
            let html = '';
            
            // Проверяем, есть ли категории
            if (Object.keys(productsByCategory).length === 0) {
                container.innerHTML = '<div class="empty-message">Товары не найдены</div>';
                this.showTemporaryMessage('Товары не найдены', 'info');
                return;
            }
            
            for (const categoryName in productsByCategory) {
                html += `<h2 class="category-heading">${categoryName}</h2>`;
                html += '<div class="products-grid two-columns-grid">';
                
                productsByCategory[categoryName].forEach(product => {
                    html += `
                    <div class="product-card" id="product-${product.id}">
                        <div class="product-image">
                            <img src="${product.image_url || '/static/images/no-image.svg'}" alt="${product.name}" loading="lazy" onerror="this.src='/static/images/no-image.svg'">
                        </div>
                        <div class="product-info">
                            <h3 class="product-name">
                                <a href="/product/${product.id}" class="product-name-link">${product.name}</a>
                            </h3>
                            <p class="product-description">${product.description || ''}</p>
                            <p class="product-price">${product.price} ₽</p>
                            ${this.createCartControlsHtml(product)}
                        </div>
                    </div>
                    `;
                });
                
                html += '</div>'; // Закрываем products-grid
            }
            
            // Отображаем товары
            container.innerHTML = html;
            
            // Показываем уведомление об успешной загрузке
            this.showTemporaryMessage(`Загружено ${products.length} товаров`, 'success', 2000);
            
        } catch (error) {
            console.error('Error loading products:', error);
            container.innerHTML = '<div class="error-message">Ошибка при загрузке товаров</div>';
            this.showTemporaryMessage('Ошибка при загрузке товаров: ' + error.message, 'error');
        }
    },

    /**
            return;
        }
        
        // Формируем HTML для категорий
        let html = '<div class="categories-grid">';
        categories.forEach(category => {
            html += `
            <div class="category-card">
                <a href="/category/${encodeURIComponent(category.name)}">
                    <div class="category-image">
                        <img src="${category.image_url || '/static/images/no-image.svg'}" alt="${category.name}" loading="lazy" onerror="this.src='/static/images/no-image.svg'">
                    </div>
                    <div class="category-name">${category.name}</div>
                </a>
            </div>`;
        });
        html += '</div>';
        
        // Отображаем категории
        container.innerHTML = html;
        
        // Показываем уведомление об успешной загрузке
        if (categories.length > 0) {
            this.showTemporaryMessage(`Загружено ${categories.length} категорий`, 'success', 2000);
        }
        
    } catch (error) {
        console.error('Error loading categories:', error);
        container.innerHTML = '<div class="error-message">Ошибка при загрузке категорий</div>';
        this.showTemporaryMessage('Ошибка при загрузке категорий: ' + error.message, 'error');
    }
},

/**
 * Загрузка и отображение всех товаров с использованием кэша
 * @param {string} containerId - ID контейнера для отображения товаров
 */
async loadAllProducts(containerId = 'products-container') {
    console.log('Loading all products with cache...');
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container with id ${containerId} not found`);
        this.showTemporaryMessage('Ошибка: контейнер для товаров не найден', 'error');
        return;
    }

    try {
        // Показываем индикатор загрузки
        container.innerHTML = '<div class="loading">Загрузка товаров...</div>';
        
        // Получаем товары из кэша или с сервера
        const products = await CacheManager.getAllProducts();
        
        // Если товаров нет, показываем сообщение
        if (!products || !Array.isArray(products) || products.length === 0) {
            container.innerHTML = '<div class="empty-message">Товары не найдены</div>';
            this.showTemporaryMessage('Товары не найдены', 'info');
            return;
        }
        
        // Проверяем, что данные имеют ожидаемую структуру
        if (!products.every(prod => prod && typeof prod === 'object' && 'id' in prod && 'name' in prod)) {
            console.error('Invalid products data structure:', products);
            container.innerHTML = '<div class="error-message">Ошибка: неверный формат данных товаров</div>';
            this.showTemporaryMessage('Ошибка: неверный формат данных товаров', 'error');
            return;
        }
        
        // Группируем товары по категориям
        const productsByCategory = {};
        products.forEach(product => {
            const categoryName = product.category_name || 'Без категории';
            if (!productsByCategory[categoryName]) {
                productsByCategory[categoryName] = [];
            }
            productsByCategory[categoryName].push(product);
        });
        
        // Формируем HTML для товаров, сгруппированных по категориям
        let html = '';
        
        // Проверяем, есть ли категории
        if (Object.keys(productsByCategory).length === 0) {
            container.innerHTML = '<div class="empty-message">Товары не найдены</div>';
            this.showTemporaryMessage('Товары не найдены', 'info');
            return;
        }
        
        for (const categoryName in productsByCategory) {
            html += `<h2 class="category-heading">${categoryName}</h2>`;
            html += '<div class="products-grid">';
            
            productsByCategory[categoryName].forEach(product => {
                html += `
                <div class="product-card" id="product-${product.id}">
                    <div class="product-image">
                        <img src="${product.image_url || '/static/images/no-image.svg'}" alt="${product.name}" loading="lazy" onerror="this.src='/static/images/no-image.svg'">
                    </div>
                    <div class="product-info">
                        <h3 class="product-name">
                            <a href="/product/${product.id}" class="product-name-link">${product.name}</a>
                        </h3>
                        <p class="product-description">${product.description || ''}</p>
                        <p class="product-price">${product.price} ₽</p>
                        ${this.createCartControlsHtml(product)}
                    </div>
                </div>
                `;
            });
            
            html += '</div>'; // Закрываем products-grid
        }
        
        // Отображаем товары
        container.innerHTML = html;
        
        // Показываем уведомление об успешной загрузке
        this.showTemporaryMessage(`Загружено ${products.length} товаров`, 'success', 2000);
        
    } catch (error) {
        console.error('Error loading products:', error);
        container.innerHTML = '<div class="error-message">Ошибка при загрузке товаров</div>';
        this.showTemporaryMessage('Ошибка при загрузке товаров: ' + error.message, 'error');
    }
},

/**
 * Загрузка и отображение товаров по категории с использованием кэша
 * @param {string} categoryName - Название категории
 * @param {string} containerId - ID контейнера для отображения товаров
 */
async loadProductsByCategory(categoryName, containerId = 'products-container') {
    console.log(`Loading products for category "${categoryName}" from cache...`);
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container with id ${containerId} not found`);
        this.showTemporaryMessage('Ошибка: контейнер для товаров не найден', 'error');
        return;
    }

    try {
        // Показываем индикатор загрузки
        container.innerHTML = '<div class="loading">Загрузка товаров категории "' + categoryName + '"...</div>';
        
        // Получаем товары по категории из кэша или с сервера
        const products = await CacheManager.getProductsByCategory(categoryName);
        
        // Если товаров нет, показываем сообщение
        if (!products || !Array.isArray(products) || products.length === 0) {
            container.innerHTML = '<div class="empty-message">Товары в категории "' + categoryName + '" не найдены</div>';
            this.showTemporaryMessage(`Товары в категории "${categoryName}" не найдены`, 'info');
            return;
        }
        
        // Проверяем, что данные имеют ожидаемую структуру
        if (!products.every(prod => prod && typeof prod === 'object' && 'id' in prod && 'name' in prod)) {
            console.error('Invalid products data structure for category:', categoryName, products);
            container.innerHTML = '<div class="error-message">Ошибка: неверный формат данных товаров</div>';
            this.showTemporaryMessage('Ошибка: неверный формат данных товаров', 'error');
            return;
        }
        
        // Формируем HTML для товаров
        let html = '<div class="products-grid two-columns-grid">';
        products.forEach(product => {
            html += `
            <div class="product-card" id="product-${product.id}">
                <div class="product-image">
                    <img src="${product.image_url || '/static/images/no-image.svg'}" alt="${product.name}" loading="lazy" onerror="this.src='/static/images/no-image.svg'">
                </div>
                <div class="product-info">
                    <h3 class="product-name">
                        <a href="/product/${product.id}" class="product-name-link">${product.name}</a>
                    </h3>
                    <p class="product-description">${product.description || ''}</p>
                    <p class="product-price">${product.price} ₽</p>
                    ${this.createCartControlsHtml(product)}
                </div>
            </div>
            `;
        });
        html += '</div>';
        
        // Отображаем товары
        container.innerHTML = html;
        
        // Показываем уведомление об успешной загрузке
        this.showTemporaryMessage(`Загружено ${products.length} товаров в категории "${categoryName}"`, 'success', 2000);
        
    } catch (error) {
        console.error('Error loading products by category:', error);
        container.innerHTML = '<div class="error-message">Ошибка при загрузке товаров</div>';
        this.showTemporaryMessage(`Ошибка при загрузке товаров категории "${categoryName}": ${error.message}`, 'error');
    }
}

// Экспортируем модуль
window.CachedDataLoader = CachedDataLoader;
