from app import create_app, db, socketio
from app.models import SpaceType, MenuItem
from decimal import Decimal
from sqlalchemy import text

app = create_app()


def seed_database():
    with app.app_context():

        db.create_all() 
        # MySQL: only add column if it doesn't exist yet.
        status_cols = db.session.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'orders'
              AND COLUMN_NAME = 'status'
        """)).fetchall()

        if not status_cols:
            db.session.execute(text("""
                ALTER TABLE orders
                ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'preparing'
            """))
            db.session.commit()

        # Add per-item status column to order_items if it doesn't exist yet.
        item_status_cols = db.session.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'order_items'
              AND COLUMN_NAME = 'status'
        """)).fetchall()

        if not item_status_cols:
            db.session.execute(text("""
                ALTER TABLE order_items
                ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'preparing'
            """))
            db.session.commit()

        # Add capacity to space_types
        cap_cols = db.session.execute(text("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'space_types' AND COLUMN_NAME = 'capacity'
        """)).fetchall()
        if not cap_cols:
            db.session.execute(text("ALTER TABLE space_types ADD COLUMN capacity INT NULL"))
            db.session.commit()

        # Add job_role to users
        jr_cols = db.session.execute(text("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'users' AND COLUMN_NAME = 'job_role'
        """)).fetchall()
        if not jr_cols:
            db.session.execute(text(
                "ALTER TABLE users ADD COLUMN job_role VARCHAR(50) NOT NULL DEFAULT 'general'"
            ))
            db.session.commit()

        # Add handled_by to orders
        hb_cols = db.session.execute(text("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'handled_by'
        """)).fetchall()
        if not hb_cols:
            db.session.execute(text("ALTER TABLE orders ADD COLUMN handled_by INT NULL"))
            db.session.commit()

        # Add number_of_people to customer_sessions
        people_cols = db.session.execute(text("""
            SELECT COLUMN_NAME FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'customer_sessions' AND COLUMN_NAME = 'number_of_people'
        """)).fetchall()
        if not people_cols:
            db.session.execute(text(
                "ALTER TABLE customer_sessions ADD COLUMN number_of_people INT NOT NULL DEFAULT 1"
            ))
            db.session.commit()

        # Add boardroom booking lifecycle columns.
        boardroom_extra_cols = {
            "session_id": "ALTER TABLE boardroom_bookings ADD COLUMN session_id INT NULL",
            "started_at": "ALTER TABLE boardroom_bookings ADD COLUMN started_at DATETIME NULL",
            "expected_end_at": "ALTER TABLE boardroom_bookings ADD COLUMN expected_end_at DATETIME NULL",
            "ended_at": "ALTER TABLE boardroom_bookings ADD COLUMN ended_at DATETIME NULL",
            "extended_minutes": "ALTER TABLE boardroom_bookings ADD COLUMN extended_minutes INT NOT NULL DEFAULT 0",
            "course": "ALTER TABLE boardroom_bookings ADD COLUMN course VARCHAR(100) NULL",
        }
        for col_name, alter_sql in boardroom_extra_cols.items():
            has_col = db.session.execute(text(f"""
                SELECT COLUMN_NAME FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'boardroom_bookings' AND COLUMN_NAME = '{col_name}'
            """)).fetchall()
            if not has_col:
                db.session.execute(text(alter_sql))
                db.session.commit()


        if SpaceType.query.count() == 0:
            regular = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
            premium = SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333"))
            boardroom = SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667"))

            db.session.add_all([regular, premium, boardroom])
            db.session.commit()

        # Default seat capacities for lounges (admin can still edit later).
        default_caps = {
            "Regular Lounge": 30,
            "Premium Lounge": 30,
        }
        for name, cap in default_caps.items():
            space = SpaceType.query.filter_by(name=name).first()
            if space and (space.capacity is None or space.capacity == 0):
                space.capacity = cap
        db.session.commit()

        # Insert (or extend) menu items.
        # If the DB already has items, we only add missing ones by `name`
        # so you don't lose existing data.
        existing_names = {name for (name,) in db.session.query(MenuItem.name).all()}

        seed_items = [
            # Main Dish - Silog
            ("Tapsilog", Decimal("95.00"), "MainDish - Silog"),
            ("Longsilog", Decimal("95.00"), "MainDish - Silog"),
            ("Hotsilog", Decimal("90.00"), "MainDish - Silog"),
            ("Tocilog", Decimal("90.00"), "MainDish - Silog"),
            ("Chicksilog", Decimal("105.00"), "MainDish - Silog"),
            ("Spamsilog", Decimal("95.00"), "MainDish - Silog"),
            ("Cornsilog", Decimal("85.00"), "MainDish - Silog"),
            ("Bangsilog", Decimal("120.00"), "MainDish - Silog"),
            ("Sisig Silog", Decimal("115.00"), "MainDish - Silog"),

            # Main Dish - Main Meals
            ("Adobo", Decimal("60.00"), "MainDish - Main Meals"),
            ("Fried Chicken", Decimal("110.00"), "MainDish - Main Meals"),
            ("Grilled Liempo", Decimal("130.00"), "MainDish - Main Meals"),
            ("Kare-Kare", Decimal("120.00"), "MainDish - Main Meals"),
            ("Bulalo", Decimal("140.00"), "MainDish - Main Meals"),
            ("Beef Caldereta", Decimal("125.00"), "MainDish - Main Meals"),

            # Main Dish - Modern Meals
            ("Burger", Decimal("50.00"), "MainDish - Modern Meals"),
            ("Chicken Sandwich", Decimal("85.00"), "MainDish - Modern Meals"),
            ("Sisig Bowl", Decimal("140.00"), "MainDish - Modern Meals"),
            ("Chicken Alfredo Bowl", Decimal("130.00"), "MainDish - Modern Meals"),
            ("Pesto Chicken Bowl", Decimal("120.00"), "MainDish - Modern Meals"),

            # Snacks - Pancit
            ("Pancit Canton", Decimal("75.00"), "Snacks - Pancit"),
            ("Pancit Bihon", Decimal("75.00"), "Snacks - Pancit"),
            ("Pancit Malabon", Decimal("95.00"), "Snacks - Pancit"),

            # Snacks - Fries & Sides
            ("Fries", Decimal("35.00"), "Snacks - Fries & Sides"),
            ("Garlic Fries", Decimal("55.00"), "Snacks - Fries & Sides"),
            ("Onion Rings", Decimal("60.00"), "Snacks - Fries & Sides"),
            ("Chicken Nuggets", Decimal("80.00"), "Snacks - Fries & Sides"),
            ("Siomai", Decimal("70.00"), "Snacks - Fries & Sides"),
            ("Kikiam", Decimal("65.00"), "Snacks - Fries & Sides"),

            # Snacks - Appetizers
            ("Lumpia Shanghai", Decimal("80.00"), "Snacks - Appetizers"),
            ("Chicharon Bulaklak", Decimal("85.00"), "Snacks - Appetizers"),
            ("Isaw", Decimal("90.00"), "Snacks - Appetizers"),
            ("Takoyaki", Decimal("95.00"), "Snacks - Appetizers"),

            # Snacks - Desserts
            ("Halo-Halo", Decimal("90.00"), "Snacks - Desserts"),
            ("Leche Flan", Decimal("80.00"), "Snacks - Desserts"),
            ("Banana Cue", Decimal("50.00"), "Snacks - Desserts"),

            # Drinks - Coffee (Hot)
            ("Hot Americano", Decimal("60.00"), "Drinks - Coffee (Hot)"),
            ("Hot Latte", Decimal("80.00"), "Drinks - Coffee (Hot)"),
            ("Hot Mocha", Decimal("95.00"), "Drinks - Coffee (Hot)"),
            ("Hot Chocolate", Decimal("100.00"), "Drinks - Coffee (Hot)"),

            # Drinks - Coffee (Cold)
            ("Iced Americano", Decimal("65.00"), "Drinks - Coffee (Cold)"),
            ("Iced Latte", Decimal("95.00"), "Drinks - Coffee (Cold)"),
            ("Iced Mocha", Decimal("110.00"), "Drinks - Coffee (Cold)"),
            ("Iced Chocolate", Decimal("110.00"), "Drinks - Coffee (Cold)"),

            # Drinks - Juices
            ("Pineapple Juice", Decimal("60.00"), "Drinks - Juices"),
            ("Calamansi Juice", Decimal("60.00"), "Drinks - Juices"),
            ("Orange Juice", Decimal("65.00"), "Drinks - Juices"),
            ("Mango Shake", Decimal("90.00"), "Drinks - Juices"),
            ("Banana Milk", Decimal("75.00"), "Drinks - Juices"),

            # Drinks - Soft Drinks
            ("Coke", Decimal("35.00"), "Drinks - Soft Drinks"),
            ("Royal", Decimal("35.00"), "Drinks - Soft Drinks"),
            ("Sprite", Decimal("35.00"), "Drinks - Soft Drinks"),

            # Compatibility (old basics if they exist as names)
            ("Juice", Decimal("30.00"), "Drinks - Juices"),
            ("Coffee", Decimal("40.00"), "Drinks - Coffee (Cold)"),
            ("Fries", Decimal("35.00"), "Snacks - Fries & Sides"),
        ]

        to_add = []
        for name, price, category in seed_items:
            if name in existing_names:
                continue
            to_add.append(MenuItem(name=name, price=price, category=category))

        # If legacy/basic items exist, align their category so the UI groups nicely.
        legacy_category_updates = {
            "Juice": "Drinks - Juices",
            "Coffee": "Drinks - Coffee (Cold)",
            "Burger": "MainDish - Modern Meals",
            "Fries": "Snacks - Fries & Sides",
            "Adobo": "MainDish - Main Meals",
        }

        for name, new_category in legacy_category_updates.items():
            if name not in existing_names:
                continue
            item = MenuItem.query.filter_by(name=name).first()
            if item and item.category != new_category:
                item.category = new_category

        if to_add:
            db.session.add_all(to_add)
        db.session.commit()


seed_database()


if __name__ == "__main__":
    socketio.run(app, debug=True)

