from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    canvas_id = db.Column(db.Integer, unique=True)
    created_date = db.Column(db.DateTime, server_default=db.func.now())
    extensions = db.relationship(
        'Extension',
        backref='user',
        lazy='dynamic'
    )
    sis_id = db.Column(db.String(50))
    sortable_name = db.Column(db.String(250))

    def __init__(self, sortable_name, canvas_id, sis_id):
        self.canvas_id = canvas_id
        self.sis_id = sis_id
        self.sortable_name = sortable_name

    def __repr__(self):
        return '<User {}>'.format(self.sortable_name)


class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    canvas_id = db.Column(db.Integer)
    course_name = db.Column(db.String(250))
    created_date = db.Column(db.DateTime, server_default=db.func.now())
    extensions = db.relationship(
        'Extension',
        backref='course',
        lazy='dynamic'
    )
    quizzes = db.relationship(
        'Quiz',
        backref='course',
        lazy='dynamic'
    )

    def __init__(self, canvas_id, course_name):
        self.canvas_id = canvas_id
        self.course_name = course_name

    def __repr__(self):
        return '<Course {}>'.format(self.course_name)


class Extension(db.Model):
    __tablename__ = 'extensions'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    created_date = db.Column(db.DateTime, server_default=db.func.now())
    percent = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    __table_args__ = (
        db.CheckConstraint(percent >= 100, name='check_percent_greater_than_100'),
    )

    def __init__(self, course_id, user_id, percent=100):
        self.course_id = course_id
        self.user_id = user_id
        self.percent = percent


class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    canvas_id = db.Column(db.Integer)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    last_updated_date = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )
    title = db.Column(db.String(250))

    def __init__(self, canvas_id, course_id, title):
        self.canvas_id = canvas_id
        self.course_id = course_id
        self.title = title
