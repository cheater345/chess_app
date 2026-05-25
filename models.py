from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
import hashlib
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    rating = db.Column(db.Integer, default=1200)
    rd = db.Column(db.Float, default=350.0)
    volatility = db.Column(db.Float, default=0.06)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    draws = db.Column(db.Integer, default=0)
    streak = db.Column(db.Integer, default=0)
    max_streak = db.Column(db.Integer, default=0)
    puzzles_solved = db.Column(db.Integer, default=0)
    puzzle_rating = db.Column(db.Integer, default=1200)
    puzzle_rd = db.Column(db.Float, default=350.0)
    join_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_guest = db.Column(db.Boolean, default=False)
    avatar_bg = db.Column(db.String(7), default='#7fa650')
    board_theme = db.Column(db.String(20), default='classic')
    piece_set = db.Column(db.String(20), default='wikipedia')
    sound_enabled = db.Column(db.Boolean, default=True)
    zen_mode = db.Column(db.Boolean, default=False)

    games_as_white = db.relationship('GameRecord', foreign_keys='GameRecord.white_id', backref='white_player', lazy='dynamic')
    games_as_black = db.relationship('GameRecord', foreign_keys='GameRecord.black_id', backref='black_player', lazy='dynamic')

    def set_password(self, password):
        salt = secrets.token_hex(16)
        self.password_hash = salt + ':' + hashlib.sha256((salt + password).encode()).hexdigest()

    def check_password(self, password):
        if ':' not in self.password_hash:
            return False
        salt, hash_val = self.password_hash.split(':', 1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == hash_val

    @property
    def total_games(self):
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self):
        if self.total_games == 0:
            return 0
        return round(self.wins / self.total_games * 100, 1)

class GameRecord(db.Model):
    __tablename__ = 'game_records'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(10), unique=True, nullable=False, index=True)
    white_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    black_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    pgn = db.Column(db.Text, default='')
    fen = db.Column(db.String(100), default='')
    result = db.Column(db.String(50), default='')
    winner = db.Column(db.String(10), nullable=True)
    termination = db.Column(db.String(30), default='')
    time_control = db.Column(db.Integer, default=600)
    rated = db.Column(db.Boolean, default=True)
    game_type = db.Column(db.String(20), default='live')
    date_played = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    white_rating_before = db.Column(db.Integer, default=1200)
    black_rating_before = db.Column(db.Integer, default=1200)
    white_rating_after = db.Column(db.Integer, default=1200)
    black_rating_after = db.Column(db.Integer, default=1200)
    moves_list = db.Column(db.Text, default='')
    white_name = db.Column(db.String(30), default='White')
    black_name = db.Column(db.String(30), default='Black')

class Puzzle(db.Model):
    __tablename__ = 'puzzles'
    id = db.Column(db.Integer, primary_key=True)
    fen = db.Column(db.String(100), nullable=False)
    solution = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=1200)
    rd = db.Column(db.Float, default=350.0)
    plays = db.Column(db.Integer, default=0)
    solves = db.Column(db.Integer, default=0)
    themes = db.Column(db.String(200), default='')
    popularity = db.Column(db.Integer, default=0)

    @property
    def difficulty(self):
        if self.rating < 1000: return 'Beginner'
        if self.rating < 1400: return 'Easy'
        if self.rating < 1800: return 'Medium'
        if self.rating < 2200: return 'Hard'
        return 'Expert'

    @property
    def solve_rate(self):
        if self.plays == 0: return 0
        return round(self.solves / self.plays * 100, 1)

class Friend(db.Model):
    __tablename__ = 'friends'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Tournament(db.Model):
    __tablename__ = 'tournaments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    format = db.Column(db.String(20), default='knockout')
    status = db.Column(db.String(20), default='open')
    max_players = db.Column(db.Integer, default=16)
    min_rating = db.Column(db.Integer, default=0)
    time_control = db.Column(db.Integer, default=600)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

class TournamentPlayer(db.Model):
    __tablename__ = 'tournament_players'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seed = db.Column(db.Integer, default=0)
    score = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)

class TournamentMatch(db.Model):
    __tablename__ = 'tournament_matches'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    white_id = db.Column(db.Integer, db.ForeignKey('tournament_players.id'), nullable=True)
    black_id = db.Column(db.Integer, db.ForeignKey('tournament_players.id'), nullable=True)
    game_id = db.Column(db.String(10), nullable=True)
    winner_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='pending')

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(10), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user = db.relationship('User', backref='chat_messages', lazy='joined')
