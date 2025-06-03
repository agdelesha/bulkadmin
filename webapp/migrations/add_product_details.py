import sqlite3
import os

# Путь к базе данных
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'products.db')

def run_migration():
    print(f"Запуск миграции для добавления полей подробной информации о товаре...")
    
    # Проверяем существование базы данных
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        return False
    
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существуют ли уже колонки
        cursor.execute("PRAGMA table_info(products)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Добавляем новые колонки, если их еще нет
        if 'detailed_info' not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN detailed_info TEXT")
            print("Добавлена колонка 'detailed_info'")
        
        if 'proteins' not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN proteins FLOAT")
            print("Добавлена колонка 'proteins'")
        
        if 'fats' not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN fats FLOAT")
            print("Добавлена колонка 'fats'")
        
        if 'carbs' not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN carbs FLOAT")
            print("Добавлена колонка 'carbs'")
        
        # Сохраняем изменения
        conn.commit()
        print("Миграция успешно выполнена!")
        
        return True
    
    except sqlite3.Error as e:
        print(f"Ошибка SQLite: {e}")
        return False
    
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_migration()
