import sqlite3

class Database:
    def __init__(self, db_name="orm_database.sqlite3"):
        self.connection = sqlite3.connect(db_name)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

    def execute(self, query, params=()):
        self.cursor.execute(query, params)
        self.connection.commit()
        return self.cursor

    def fetchall(self, query, params=()):
        return self.execute(query, params).fetchall()

db = Database()

class Field:
    def __init__(self, primary_key=False, null=False):
        self.primary_key = primary_key
        self.null = null
        self.name = None 

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__.get(self.name)

    def __set__(self, instance, value):
        if not self.null and value is None and not self.primary_key:
            raise ValueError(f"{self.name} cannot be null.")
        instance.__dict__[self.name] = value

class CharField(Field):
    field_type = "TEXT"
    
    def __set__(self, instance, value):
        if value is not None and not isinstance(value, str):
            raise TypeError(f"{self.name} must be a string.")
        super().__set__(instance, value)

class IntegerField(Field):
    field_type = "INTEGER"
    
    def __set__(self, instance, value):
        if value is not None and not isinstance(value, int):
            raise TypeError(f"{self.name} must be an integer.")
        super().__set__(instance, value)

class ForeignKey(Field):
    field_type = "INTEGER"

    def __init__(self, to_model, **kwargs):
        super().__init__(**kwargs)
        self.to_model = to_model

    def __get__(self, instance, owner):
        if instance is None:
            return self
        
        fk_id = instance.__dict__.get(self.name)
        if fk_id is None:
            return None
            
        return self.to_model.objects.filter(id=fk_id).first()

    def __set__(self, instance, value):
        if isinstance(value, self.to_model):
            instance.__dict__[self.name] = getattr(value, "id", None)
        else:
            super().__set__(instance, value)

class QuerySet:
    def __init__(self, model_class):
        self.model_class = model_class
        self.where_clauses = []
        self.params = []
        self.order_clause = ""

    def filter(self, **kwargs):
        for key, value in kwargs.items():
            if "__gte" in key:
                col = key.replace("__gte", "")
                self.where_clauses.append(f"{col} >= ?")
            elif "__lte" in key:
                col = key.replace("__lte", "")
                self.where_clauses.append(f"{col} <= ?")
            else:
                self.where_clauses.append(f"{key} = ?")
            self.params.append(value)
        return self

    def order_by(self, field_name):
        if field_name.startswith("-"):
            self.order_clause = f"ORDER BY {field_name[1:]} DESC"
        else:
            self.order_clause = f"ORDER BY {field_name} ASC"
        return self

    def _build_query(self):
        query = f"SELECT * FROM {self.model_class.__tablename__}"
        if self.where_clauses:
            query += " WHERE " + " AND ".join(self.where_clauses)
        if self.order_clause:
            query += f" {self.order_clause}"
        return query

    def all(self):
        query = self._build_query()
        rows = db.fetchall(query, tuple(self.params))
        return [self.model_class(**dict(row)) for row in rows]

    def first(self):
        results = self.all()
        return results[0] if results else None

class ModelMeta(type):
    def __new__(mcs, name, bases, attrs):
        if name == "Model":
            fields = {}
            for key, value in attrs.items():
                if isinstance(value, Field):
                    fields[key] = value
            attrs["_fields"] = fields
            return super().__new__(mcs, name, bases, attrs)

        table_name = name.lower()
        attrs["__tablename__"] = table_name
        
        fields = {}
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)

        for key, value in attrs.items():
            if isinstance(value, Field):
                fields[key] = value
        
        attrs["_fields"] = fields
        cls = super().__new__(mcs, name, bases, attrs)
        cls.objects = QuerySet(cls)

        columns = []
        for field_name, field in fields.items():
            col_def = f"{field_name} {field.field_type}"
            if field.primary_key:
                col_def += " PRIMARY KEY AUTOINCREMENT"
            elif not field.null:
                col_def += " NOT NULL"
            columns.append(col_def)

        create_table_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)});"
        db.execute(create_table_sql)
        
        return cls

class Model(metaclass=ModelMeta):
    id = IntegerField(primary_key=True)

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def save(self):
        fields = {k: self.__dict__.get(k) for k in self._fields.keys() if k != 'id'}
        
        if getattr(self, "id", None) is None:
            cols = ", ".join(fields.keys())
            placeholders = ", ".join(["?"] * len(fields))
            query = f"INSERT INTO {self.__tablename__} ({cols}) VALUES ({placeholders})"
            cursor = db.execute(query, tuple(fields.values()))
            self.id = cursor.lastrowid
        else:
            set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
            query = f"UPDATE {self.__tablename__} SET {set_clause} WHERE id = ?"
            params = list(fields.values()) + [self.id]
            db.execute(query, tuple(params))

    def delete(self):
        if hasattr(self, "id") and self.id is not None:
            query = f"DELETE FROM {self.__tablename__} WHERE id = ?"
            db.execute(query, (self.id,))

    def __repr__(self):
        return f"<{self.__class__.__name__} id={getattr(self, 'id', None)}>"# 1. Define Models
class Department(Model):
    name = CharField()

class User(Model):
    name = CharField()
    age = IntegerField()
    department = ForeignKey(to_model=Department)

# 2. CRUD Operations
# Create and save a department
engineering = Department(name="Engineering")
engineering.save()

# Create and save users
alice = User(name="Alice", age=28, department=engineering)
alice.save()

bob = User(name="Bob", age=22, department=engineering)
bob.save()

charlie = User(name="Charlie", age=30, department=engineering)
charlie.save()

# 3. Chained Queries
results = User.objects.filter(age__gte=25).order_by("-name").all()

print("Filtered & Ordered Users:")
for user in results:
    print(f"- {user.name} (Age: {user.age})")

# 4. Lazy Loading the ForeignKey relationship
first_user = results[0]
print(f"\nLazy Loading Department for {first_user.name}:")
print(f"Department Name: {first_user.department.name}")