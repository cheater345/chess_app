import eventlet
eventlet.monkey_patch()

import uuid
import threading
import time
import json
import os
import math
import random
from datetime import datetime, timezone

from flask import Flask, render_template, session, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import chess
import chess.pgn

from models import db, User, GameRecord, Puzzle, Friend, Tournament, TournamentPlayer, TournamentMatch, ChatMessage

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "chess-app-secret-key-change-in-production")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///chess_app.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_TYPE"] = "filesystem"

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
login_manager = LoginManager(app)
login_manager.login_view = 'login'

games = {}
waiting_players = {}

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

PIECE_SYMBOLS = {'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
                 'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'}

OPENING_BOOK = {}
_OPENING_BOOK_LOADED = False

def load_opening_book():
    global _OPENING_BOOK_LOADED, OPENING_BOOK
    if _OPENING_BOOK_LOADED:
        return
    openings = [
        ["e4", "e5", "Nf3", "Nc6", "Bb5"],
        ["e4", "e5", "Nf3", "Nc6", "Bc4"],
        ["e4", "e5", "Nf3", "Nc6", "d4"],
        ["e4", "e5", "Nf3", "Nf6"],
        ["e4", "e5", "f4"],
        ["e4", "c5"],
        ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3"],
        ["e4", "c5", "Nf3", "Nc6", "d4", "cxd4", "Nxd4"],
        ["e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5"],
        ["e4", "e6", "d4", "d5", "Nd2"],
        ["e4", "d5"],
        ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4"],
        ["d4", "d5", "c4"],
        ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5"],
        ["d4", "d5", "c4", "c6"],
        ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6"],
        ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4"],
        ["Nf3", "Nf6", "c4", "g6"],
        ["c4", "e5"],
        ["c4", "c5"],
        ["e4", "d6", "d4", "Nf6", "Nc3", "g6"],
        ["e4", "g6", "d4", "Bg7", "Nc3", "d6"],
        ["d4", "f5"],
        ["d4", "d5", "Nc3", "Nf6", "Bg5"],
    ]
    for moves in openings:
        board = chess.Board()
        key = board.fen()
        move_list = []
        for m in moves:
            try:
                move = board.parse_san(m)
                move_list.append(move.uci())
                board.push(move)
            except:
                break
        if move_list:
            OPENING_BOOK[key] = move_list

    _OPENING_BOOK_LOADED = True

class SimpleChessAI:
    PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}

    PAWN_TABLE = [0,0,0,0,0,0,0,0,50,50,50,50,50,50,50,50,10,10,20,30,30,20,10,10,5,5,10,25,25,10,5,5,0,0,0,20,20,0,0,0,5,-5,-10,0,0,-10,-5,5,5,10,10,-20,-20,10,10,5,0,0,0,0,0,0,0,0]
    KNIGHT_TABLE = [-50,-40,-30,-30,-30,-30,-40,-50,-40,-20,0,0,0,0,-20,-40,-30,0,10,15,15,10,0,-30,-30,5,15,20,20,15,5,-30,-30,0,15,20,20,15,0,-30,-30,5,10,15,15,10,5,-30,-40,-20,0,5,5,0,-20,-40,-50,-40,-30,-30,-30,-30,-40,-50]
    BISHOP_TABLE = [-20,-10,-10,-10,-10,-10,-10,-20,-10,0,0,0,0,0,0,-10,-10,0,10,10,10,10,0,-10,-10,5,5,10,10,5,5,-10,-10,0,10,10,10,10,0,-10,-10,10,10,10,10,10,10,-10,-10,5,0,0,0,0,5,-10,-20,-10,-10,-10,-10,-10,-10,-20]
    ROOK_TABLE = [0,0,0,0,0,0,0,0,5,10,10,10,10,10,10,5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,-5,0,0,0,0,0,0,-5,0,0,0,5,5,0,0,0]
    QUEEN_TABLE = [-20,-10,-10,-5,-5,-10,-10,-20,-10,0,0,0,0,0,0,-10,-10,0,5,5,5,5,0,-10,-5,0,5,5,5,5,0,-5,0,0,5,5,5,5,0,-5,-10,5,5,5,5,5,0,-10,-10,0,5,0,0,0,0,-10,-20,-10,-10,-5,-5,-10,-10,-20]
    KING_TABLE_BASE = [-30,-40,-40,-50,-50,-40,-40,-30,-30,-40,-40,-50,-50,-40,-40,-30,-30,-40,-40,-50,-50,-40,-40,-30,-30,-40,-40,-50,-50,-40,-40,-30,-20,-30,-30,-40,-40,-30,-30,-20,-10,-20,-20,-20,-20,-20,-20,-10,20,20,0,0,0,0,20,20,20,30,10,0,0,10,30,20]
    KING_TABLE_END = [-50,-40,-30,-20,-20,-30,-40,-50,-30,-20,-10,0,0,-10,-20,-30,-30,-10,20,30,30,20,-10,-30,-30,-10,30,40,40,30,-10,-30,-30,-10,30,40,40,30,-10,-30,-30,-10,20,30,30,20,-10,-30,-30,-30,-10,0,0,-10,-30,-30,-50,-40,-30,-20,-20,-30,-40,-50]

    PST = {chess.PAWN: PAWN_TABLE, chess.KNIGHT: KNIGHT_TABLE, chess.BISHOP: BISHOP_TABLE, chess.ROOK: ROOK_TABLE, chess.QUEEN: QUEEN_TABLE, chess.KING: KING_TABLE_BASE}

    DEPTH_MAP = {'beginner': 1, 'intermediate': 2, 'advanced': 3, 'master': 4, 'grandmaster': 5}

    def __init__(self, difficulty='intermediate'):
        self.difficulty = difficulty
        self.nodes_searched = 0
        self.time_limit = 5.0
        self.start_time = 0
        load_opening_book()

    def get_depth(self):
        return self.DEPTH_MAP.get(self.difficulty, 2)

    def get_opening_move(self, board):
        fen = board.fen()
        book = OPENING_BOOK.get(fen)
        if book and len(book) > 0:
            move = book[0]
            try:
                return chess.Move.from_uci(move)
            except:
                pass
        return None

    def evaluate(self, board):
        if board.is_checkmate():
            return -100000 if board.turn == chess.WHITE else 100000
        if board.is_stalemate() or board.is_insufficient_material():
            return 0

        score = 0
        total_pieces = 0
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece is None:
                continue
            total_pieces += 1
            val = self.PIECE_VALUES[piece.piece_type]
            pst = self._position_value(piece, sq)
            if piece.color == chess.WHITE:
                score += val + pst
            else:
                score -= val + pst

        if total_pieces <= 8:
            score += self._king_endgame_eval(board)
        else:
            score += self._king_safety(board)
            score += self._pawn_structure(board)

        score += self._mobility(board) * 5
        return score

    def _position_value(self, piece, square):
        table = self.PST.get(piece.piece_type)
        if table is None:
            return 0
        row, col = divmod(square, 8)
        if piece.color == chess.WHITE:
            return table[56 - (row * 8 + col)]
        return table[row * 8 + col]

    def _king_endgame_eval(self, board):
        score = 0
        wk_sq = board.king(chess.WHITE)
        bk_sq = board.king(chess.BLACK)
        if wk_sq is None or bk_sq is None:
            return 0
        wr, wc = divmod(wk_sq, 8)
        br, bc = divmod(bk_sq, 8)
        dist = abs(wr - br) + abs(wc - bc)
        score += (14 - dist) * 10
        center_dist = abs(wr - 3.5) + abs(wc - 3.5)
        score += (7 - center_dist) * 5
        return score

    def _king_safety(self, board):
        score = 0
        for color in [chess.WHITE, chess.BLACK]:
            king_sq = board.king(color)
            if king_sq is None:
                continue
            row, col = divmod(king_sq, 8)
            shield = 0
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = row + dr, col + dc
                    if 0 <= nr < 8 and 0 <= nc < 8:
                        p = board.piece_at(nr * 8 + nc)
                        if p and p.color == color and p.piece_type == chess.PAWN:
                            shield += 1
            mult = 1 if color == chess.WHITE else -1
            score += shield * 15 * mult
        return score

    def _pawn_structure(self, board):
        score = 0
        for color in [chess.WHITE, chess.BLACK]:
            pawns = [sq for sq in chess.SQUARES if board.piece_at(sq) and board.piece_at(sq).piece_type == chess.PAWN and board.piece_at(sq).color == color]
            mult = 1 if color == chess.WHITE else -1
            files = set(sq % 8 for sq in pawns)
            score -= (len(pawns) - len(files)) * 15 * mult
            for sq in pawns:
                row = sq // 8
                col = sq % 8
                for dc in [-1, 1]:
                    nc = col + dc
                    if 0 <= nc < 8:
                        np = board.piece_at(row * 8 + nc)
                        if np and np.piece_type == chess.PAWN and np.color == color:
                            score += 5 * mult
        return score

    def _mobility(self, board):
        w_mob = sum(1 for m in board.legal_moves if board.color_at(m.from_square) == chess.WHITE)
        b_mob = sum(1 for m in board.legal_moves if board.color_at(m.from_square) == chess.BLACK)
        return (w_mob - b_mob) / 10

    def minimax(self, board, depth, alpha, beta, maximizing, quiescent=False):
        self.nodes_searched += 1
        if depth == 0:
            if quiescent:
                return self._quiescence_search(board, alpha, beta, maximizing)
            return self.evaluate(board)
        if board.is_game_over():
            return self.evaluate(board)

        if maximizing:
            max_eval = -float('inf')
            moves = self._order_moves(board, list(board.legal_moves))
            for move in moves:
                board.push(move)
                eval_score = self.minimax(board, depth - 1, alpha, beta, False, quiescent)
                board.pop()
                if eval_score > max_eval:
                    max_eval = eval_score
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval
        else:
            min_eval = float('inf')
            moves = self._order_moves(board, list(board.legal_moves))
            for move in moves:
                board.push(move)
                eval_score = self.minimax(board, depth - 1, alpha, beta, True, quiescent)
                board.pop()
                if eval_score < min_eval:
                    min_eval = eval_score
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval

    def _quiescence_search(self, board, alpha, beta, maximizing):
        stand_pat = self.evaluate(board)
        if maximizing:
            if stand_pat >= beta:
                return beta
            if stand_pat > alpha:
                alpha = stand_pat
        else:
            if stand_pat <= alpha:
                return alpha
            if stand_pat < beta:
                beta = stand_pat

        moves = [m for m in board.legal_moves if board.is_capture(m)]
        if not moves:
            return stand_pat
        moves = self._order_moves(board, moves)

        if maximizing:
            max_eval = stand_pat
            for move in moves:
                board.push(move)
                eval_score = self._quiescence_search(board, alpha, beta, False)
                board.pop()
                if eval_score > max_eval:
                    max_eval = eval_score
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval
        else:
            min_eval = stand_pat
            for move in moves:
                board.push(move)
                eval_score = self._quiescence_search(board, alpha, beta, True)
                board.pop()
                if eval_score < min_eval:
                    min_eval = eval_score
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval

    def _order_moves(self, board, moves):
        def priority(m):
            p = 0
            captured = board.piece_at(m.to_square)
            if captured:
                attacker = board.piece_at(m.from_square)
                if attacker:
                    p += 10 * self.PIECE_VALUES.get(captured.piece_type, 0) - self.PIECE_VALUES.get(attacker.piece_type, 0) // 100
            if m.promotion:
                p += 1000
            if board.gives_check(m):
                p += 100
            piece = board.piece_at(m.from_square)
            if piece and piece.piece_type == chess.PAWN:
                p += 20
            return -p
        moves.sort(key=priority)
        return moves

    def get_best_move(self, board):
        opening = self.get_opening_move(board)
        if opening:
            return opening

        depth = self.get_depth()
        self.nodes_searched = 0
        best_move = None
        best_value = -float('inf') if board.turn == chess.WHITE else float('inf')

        moves = self._order_moves(board, list(board.legal_moves))
        for move in moves:
            board.push(move)
            value = self.minimax(board, depth - 1, -float('inf'), float('inf'), board.turn == chess.BLACK, quiescent=True)
            board.pop()
            if board.turn == chess.WHITE:
                if value > best_value:
                    best_value = value
                    best_move = move
            else:
                if value < best_value:
                    best_value = value
                    best_move = move
        return best_move


class ChessGame:
    def __init__(self, game_id, time_control=600, game_type='live'):
        self.id = game_id
        self.board = chess.Board()
        self.players = {}
        self.white_sid = None
        self.black_sid = None
        self.white_name = "White"
        self.black_name = "Black"
        self.white_id = None
        self.black_id = None
        self.white_rating = 1200
        self.black_rating = 1200
        self.status = "waiting"
        self.move_history = []
        self.move_ucis = []
        self.captured_pieces = {"white": [], "black": []}
        self.time_control = time_control
        self.timers = {"white": time_control, "black": time_control}
        self.last_move_time = time.time()
        self.is_ai = False
        self.ai_difficulty = None
        self.game_type = game_type
        self.increment = 0
        self.result_reason = None
        self.draw_offered_by = None
        self.white_rating_before = 1200
        self.black_rating_before = 1200

    def add_player(self, sid, name, user_id=None, rating=1200):
        if self.white_sid is None:
            self.white_sid = sid
            self.white_name = name
            self.white_id = user_id
            self.white_rating = rating
            self.white_rating_before = rating
            self.players[sid] = "white"
            return "white"
        elif self.black_sid is None and sid != self.white_sid:
            self.black_sid = sid
            self.black_name = name
            self.black_id = user_id
            self.black_rating = rating
            self.black_rating_before = rating
            self.players[sid] = "black"
            self.status = "active"
            return "black"
        return None

    def setup_ai(self, sid, name, user_id, rating, difficulty, time_control=600, game_type='live'):
        self.is_ai = True
        self.ai_difficulty = difficulty
        self.white_sid = sid
        self.white_name = name
        self.white_id = user_id
        self.white_rating = rating
        self.white_rating_before = rating
        self.black_sid = "ai"
        self.black_name = f"Computer ({difficulty.capitalize()})"
        self.black_id = None
        self.black_rating = rating
        self.players[sid] = "white"
        self.players["ai"] = "black"
        self.status = "active"
        self.time_control = time_control
        self.timers = {"white": time_control, "black": time_control}
        self.last_move_time = time.time()
        self.game_type = game_type
        return "white"

    def _tick_timer(self, color):
        elapsed = time.time() - self.last_move_time
        self.timers[color] = max(0, round(self.timers[color] - elapsed, 1))
        self.last_move_time = time.time()
        if self.timers[color] <= 0:
            self.status = "finished"
            winner = "black" if color == "white" else "white"
            self.result_reason = f"{winner} wins on time"
            return True
        return False

    def make_move(self, sid, move_uci):
        if self.status != "active":
            return {"error": "Game is not active"}
        color = self.players.get(sid)
        if color is None:
            return {"error": "You are not in this game"}
        if (self.board.turn == chess.WHITE and color != "white") or (self.board.turn == chess.BLACK and color != "black"):
            return {"error": "Not your turn"}
        try:
            move = chess.Move.from_uci(move_uci)
            if move not in self.board.legal_moves:
                return {"error": "Illegal move"}
            timed_out = self._tick_timer(color)
            if timed_out:
                return self._make_result(game_over=True)
            captured = self.board.piece_at(move.to_square)
            san = self.board.san(move)
            self.board.push(move)
            self.move_history.append(san)
            self.move_ucis.append(move_uci)
            if captured:
                cap_color = "white" if color == "black" else "black"
                self.captured_pieces[cap_color].append(captured.symbol())
            result, game_over = self._check_game_over()
            if game_over:
                self.status = "finished"
                self.result_reason = result
            return self._make_result(game_over, result, san)
        except Exception as e:
            return {"error": str(e)}

    def make_ai_move(self, move_uci):
        try:
            move = chess.Move.from_uci(move_uci)
            if move not in self.board.legal_moves:
                return {"error": "Illegal move"}
            timed_out = self._tick_timer("black")
            if timed_out:
                return self._make_result(game_over=True)
            captured = self.board.piece_at(move.to_square)
            san = self.board.san(move)
            self.board.push(move)
            self.move_history.append(san)
            self.move_ucis.append(move_uci)
            if captured:
                self.captured_pieces["white"].append(captured.symbol())
            result, game_over = self._check_game_over()
            if game_over:
                self.status = "finished"
                self.result_reason = result
            res = self._make_result(game_over, result, san)
            res["ai_move"] = True
            return res
        except Exception as e:
            return {"error": str(e)}

    def _make_result(self, game_over, result=None, san=None):
        return {
            "success": True,
            "san": san,
            "fen": self.board.fen(),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "game_over": game_over,
            "result": result or self.result_reason,
            "in_check": self.board.is_check(),
            "move_history": self.move_history,
            "move_ucis": self.move_ucis,
            "captured_white": self.captured_pieces["white"],
            "captured_black": self.captured_pieces["black"],
            "legal_moves": [m.uci() for m in self.board.legal_moves] if not game_over else [],
            "timers": self.timers,
        }

    def _check_game_over(self):
        if not self.board.is_game_over():
            return None, False
        if self.board.is_checkmate():
            winner = "black" if self.board.turn == chess.WHITE else "white"
            return f"{winner} wins by checkmate", True
        elif self.board.is_stalemate():
            return "draw by stalemate", True
        elif self.board.is_insufficient_material():
            return "draw by insufficient material", True
        elif self.board.is_seventyfive_moves():
            return "draw by 75-move rule", True
        elif self.board.is_fivefold_repetition():
            return "draw by repetition", True
        return "draw", True

    def get_state(self):
        result = getattr(self, 'result_reason', None) or self._get_result_from_board()
        return {
            "id": self.id,
            "fen": self.board.fen(),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "status": self.status,
            "white_name": self.white_name,
            "black_name": self.black_name,
            "white_rating": self.white_rating,
            "black_rating": self.black_rating,
            "move_history": self.move_history,
            "move_ucis": self.move_ucis,
            "captured_white": self.captured_pieces["white"],
            "captured_black": self.captured_pieces["black"],
            "in_check": self.board.is_check(),
            "legal_moves": [m.uci() for m in self.board.legal_moves] if self.status == "active" else [],
            "has_white": self.white_sid is not None,
            "has_black": self.black_sid is not None,
            "result": result,
            "is_ai": self.is_ai,
            "ai_difficulty": self.ai_difficulty,
            "timers": self.timers,
            "time_control": self.time_control,
            "game_type": self.game_type,
        }

    def _get_result_from_board(self):
        if self.status != "finished":
            return None
        if self.board.is_checkmate():
            winner = "black" if self.board.turn == chess.WHITE else "white"
            return f"{winner} wins by checkmate"
        elif self.board.is_stalemate():
            return "draw by stalemate"
        elif self.board.is_insufficient_material():
            return "draw by insufficient material"
        elif self.board.is_seventyfive_moves():
            return "draw by 75-move rule"
        elif self.board.is_fivefold_repetition():
            return "draw by repetition"
        return "draw"

    def get_pgn(self):
        game = chess.pgn.Game()
        game.headers["Event"] = "Chess Game"
        game.headers["Site"] = "Chess App"
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Round"] = "1"
        game.headers["White"] = self.white_name
        game.headers["Black"] = self.black_name
        game.headers["Result"] = self._get_pgn_result()
        game.headers["TimeControl"] = str(self.time_control)
        game.headers["GameType"] = self.game_type
        node = game
        for move_uci in self.move_ucis:
            try:
                move = chess.Move.from_uci(move_uci)
                if move in self.board.legal_moves or True:
                    san = self.board.san(move)
                    self.board.push(move)
                    node = node.add_variation(move)
            except:
                break
        self.board = chess.Board()
        return str(game)

    def _get_pgn_result(self):
        r = getattr(self, 'result_reason', None) or self._get_result_from_board()
        if not r:
            return "*"
        if "wins" in r:
            w = r.split(" wins")[0]
            return "1-0" if w == "white" else "0-1"
        return "1/2-1/2"


# ============== RATING SYSTEM ==============

def expected_score(rating_a, rating_b):
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))

def update_ratings(winner, loser, draw=False):
    if draw:
        expected_w = expected_score(winner.rating, loser.rating)
        expected_l = expected_score(loser.rating, winner.rating)
        k = 32 - min(winner.total_games // 20, 12)
        winner.rating += round(k * (0.5 - expected_w))
        loser.rating += round(k * (0.5 - expected_l))
    else:
        expected_w = expected_score(winner.rating, loser.rating)
        expected_l = expected_score(loser.rating, winner.rating)
        k_w = 32 - min(winner.total_games // 20, 12)
        k_l = 32 - min(loser.total_games // 20, 12)
        winner.rating += round(k_w * (1.0 - expected_w))
        loser.rating += round(k_l * (0.0 - expected_l))
        winner.rating = max(100, winner.rating)
        loser.rating = max(100, loser.rating)


# ============== PUZZLE SYSTEM ==============

def create_default_puzzles():
    if Puzzle.query.count() > 0:
        return
    puzzles = [
        ("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 0 1", ["f7f8q"], 800, "mate"),
        ("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 1", ["e5d4"], 600, "fork"),
        ("r4rk1/pp1nqppp/2p5/3pPb2/2PP4/2N2N2/PP3PPP/R1BQR1K1 w - - 0 1", ["e5c7"], 1200, "fork"),
        ("r1bq1rk1/ppp2ppp/2np4/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 1", ["c4f7","f7e8","e8f8","f8g8"], 1400, "sacrifice"),
        ("r4rk1/1pp2ppp/p1p5/3q4/2P1n3/2N5/PPQ2PPP/R1R3K1 w - - 0 1", ["c3e4","d5e4","c2e4"], 1600, "sacrifice"),
        ("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 0 1", ["c4f7","e8f7","f3e5","f7e8","e5f7"], 1800, "sacrifice"),
        ("r1b1kb1r/pppp1ppp/2n2n2/4p3/2B1P3/2NP4/PPP2PPP/R1BQK1NR w KQkq - 0 1", ["c4f7","e8f7","d3g6","f7g6","g1f3"], 2000, "sacrifice"),
    ]
    for fen, solution, rating, themes in puzzles:
        p = Puzzle(fen=fen, solution=json.dumps(solution), rating=rating, themes=themes, plays=0, solves=0)
        db.session.add(p)
    db.session.commit()


# ============== FLASK ROUTES ==============

@app.route("/")
def index():
    if "username" not in session:
        session["username"] = f"Player{uuid.uuid4().hex[:4]}"
    guest = True
    if current_user.is_authenticated:
        guest = False
        session["username"] = current_user.username
    return render_template("index.html", guest=guest)

@app.route("/game/<game_id>")
def game_page(game_id):
    if "username" not in session:
        session["username"] = f"Player{uuid.uuid4().hex[:4]}"
    return render_template("index.html", game_id=game_id)

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"error": "All fields required"}), 400
    if len(username) < 3 or len(username) > 30:
        return jsonify({"error": "Username 3-30 characters"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username taken"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password min 6 characters"}), 400

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    session["username"] = username
    return jsonify({"success": True, "username": username, "rating": user.rating})

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    login_user(user)
    session["username"] = username
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"success": True, "username": username, "rating": user.rating})

@app.route("/api/logout")
@login_required
def api_logout():
    logout_user()
    session["username"] = f"Player{uuid.uuid4().hex[:4]}"
    return jsonify({"success": True})

@app.route("/api/guest")
def api_guest():
    guest_name = f"Guest{uuid.uuid4().hex[:4]}"
    session["username"] = guest_name
    return jsonify({"success": True, "username": guest_name})

@app.route("/api/profile/<username>")
def api_profile(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "username": user.username,
        "rating": user.rating,
        "wins": user.wins,
        "losses": user.losses,
        "draws": user.draws,
        "total_games": user.total_games,
        "win_rate": user.win_rate,
        "streak": user.streak,
        "max_streak": user.max_streak,
        "puzzle_rating": user.puzzle_rating,
        "puzzles_solved": user.puzzles_solved,
        "join_date": user.join_date.isoformat() if user.join_date else "",
        "board_theme": user.board_theme,
        "piece_set": user.piece_set,
    })

@app.route("/api/leaderboard")
def api_leaderboard():
    users = User.query.filter_by(is_guest=False).order_by(User.rating.desc()).limit(100).all()
    return jsonify([{
        "rank": i + 1,
        "username": u.username,
        "rating": u.rating,
        "wins": u.wins,
        "losses": u.losses,
        "draws": u.draws,
        "win_rate": u.win_rate,
    } for i, u in enumerate(users)])

@app.route("/api/games/<username>")
def api_user_games(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    games_list = GameRecord.query.filter(
        (GameRecord.white_id == user.id) | (GameRecord.black_id == user.id)
    ).order_by(GameRecord.date_played.desc()).limit(50).all()
    return jsonify([{
        "game_id": g.game_id,
        "white": g.white_name,
        "black": g.black_name,
        "result": g.result,
        "winner": g.winner,
        "time_control": g.time_control,
        "date": g.date_played.isoformat() if g.date_played else "",
        "rated": g.rated,
        "pgn": g.pgn,
        "moves": json.loads(g.moves_list) if g.moves_list else [],
    } for g in games_list])

@app.route("/api/game/<game_id>")
def api_game_detail(game_id):
    record = GameRecord.query.filter_by(game_id=game_id).first()
    if not record:
        return jsonify({"error": "Game not found"}), 404
    return jsonify({
        "game_id": record.game_id,
        "white": record.white_name,
        "black": record.black_name,
        "result": record.result,
        "winner": record.winner,
        "termination": record.termination,
        "time_control": record.time_control,
        "rated": record.rated,
        "date": record.date_played.isoformat() if record.date_played else "",
        "pgn": record.pgn,
        "fen": record.fen,
        "moves": json.loads(record.moves_list) if record.moves_list else [],
        "white_rating_before": record.white_rating_before,
        "black_rating_before": record.black_rating_before,
        "white_rating_after": record.white_rating_after,
        "black_rating_after": record.black_rating_after,
    })

@app.route("/api/puzzles/daily")
def api_daily_puzzle():
    puzzle = Puzzle.query.order_by(Puzzle.plays.asc()).first()
    if not puzzle:
        return jsonify({"error": "No puzzles available"}), 404
    return jsonify({
        "id": puzzle.id,
        "fen": puzzle.fen,
        "solution": json.loads(puzzle.solution),
        "rating": puzzle.rating,
        "themes": puzzle.themes,
        "plays": puzzle.plays,
        "solves": puzzle.solves,
        "solve_rate": puzzle.solve_rate,
    })

@app.route("/api/puzzles/<int:puzzle_id>")
def api_get_puzzle(puzzle_id):
    puzzle = db.session.get(Puzzle, puzzle_id)
    if not puzzle:
        return jsonify({"error": "Puzzle not found"}), 404
    return jsonify({
        "id": puzzle.id,
        "fen": puzzle.fen,
        "solution": json.loads(puzzle.solution),
        "rating": puzzle.rating,
        "themes": puzzle.themes,
        "plays": puzzle.plays,
        "solves": puzzle.solves,
    })

@app.route("/api/puzzles/random")
def api_random_puzzle():
    theme = request.args.get("theme", "")
    query = Puzzle.query
    if theme:
        query = query.filter(Puzzle.themes.contains(theme))
    puzzle = query.order_by(db.func.random()).first()
    if not puzzle:
        return jsonify({"error": "No puzzles found"}), 404
    return jsonify({
        "id": puzzle.id,
        "fen": puzzle.fen,
        "solution": json.loads(puzzle.solution),
        "rating": puzzle.rating,
        "themes": puzzle.themes,
    })

@app.route("/api/puzzles/<int:puzzle_id>/result", methods=["POST"])
def api_puzzle_result(puzzle_id):
    data = request.json
    solved = data.get("solved", False)
    puzzle = db.session.get(Puzzle, puzzle_id)
    if not puzzle:
        return jsonify({"error": "Puzzle not found"}), 404
    puzzle.plays += 1
    if solved:
        puzzle.solves += 1
    if current_user.is_authenticated:
        if solved:
            current_user.puzzles_solved += 1
            current_user.puzzle_rating += 5
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/friends/search")
def api_friend_search():
    q = request.args.get("q", "")
    if len(q) < 2:
        return jsonify([])
    users = User.query.filter(User.username.ilike(f"%{q}%")).limit(20).all()
    return jsonify([{"id": u.id, "username": u.username, "rating": u.rating} for u in users])

@app.route("/api/friends")
def api_friends():
    if not current_user.is_authenticated:
        return jsonify([])
    friends = Friend.query.filter(
        ((Friend.user_id == current_user.id) | (Friend.friend_id == current_user.id)),
        Friend.status == "accepted"
    ).all()
    result = []
    for f in friends:
        uid = f.friend_id if f.user_id == current_user.id else f.user_id
        u = db.session.get(User, uid)
        if u:
            result.append({"id": u.id, "username": u.username, "rating": u.rating})
    return jsonify(result)

@app.route("/api/friends/add", methods=["POST"])
def api_add_friend():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    friend_id = data.get("user_id")
    if not friend_id or friend_id == current_user.id:
        return jsonify({"error": "Invalid user"}), 400
    existing = Friend.query.filter_by(user_id=current_user.id, friend_id=friend_id).first()
    if existing:
        return jsonify({"error": "Already friends or request pending"}), 400
    f = Friend(user_id=current_user.id, friend_id=friend_id, status="accepted")
    db.session.add(f)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/friends/remove", methods=["POST"])
def api_remove_friend():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    friend_id = data.get("user_id")
    f = Friend.query.filter(
        ((Friend.user_id == current_user.id) & (Friend.friend_id == friend_id)) |
        ((Friend.user_id == friend_id) & (Friend.friend_id == current_user.id))
    ).first()
    if f:
        db.session.delete(f)
        db.session.commit()
    return jsonify({"success": True})

@app.route("/api/tournaments")
def api_tournaments():
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).limit(20).all()
    return jsonify([{
        "id": t.id,
        "name": t.name,
        "format": t.format,
        "status": t.status,
        "max_players": t.max_players,
        "player_count": TournamentPlayer.query.filter_by(tournament_id=t.id).count(),
        "time_control": t.time_control,
        "created_by": t.created_by,
    } for t in tournaments])

@app.route("/api/tournaments/create", methods=["POST"])
def api_create_tournament():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401
    data = request.json
    t = Tournament(
        name=data.get("name", "Tournament"),
        format=data.get("format", "knockout"),
        max_players=data.get("max_players", 16),
        time_control=data.get("time_control", 600),
        created_by=current_user.id,
    )
    db.session.add(t)
    db.session.commit()
    tp = TournamentPlayer(tournament_id=t.id, user_id=current_user.id, seed=0)
    db.session.add(tp)
    db.session.commit()
    return jsonify({"success": True, "id": t.id})

@app.route("/api/tournaments/<int:tid>/join", methods=["POST"])
def api_join_tournament(tid):
    if not current_user.is_authenticated:
        return jsonify({"error": "Not logged in"}), 401
    t = db.session.get(Tournament, tid)
    if not t or t.status != "open":
        return jsonify({"error": "Tournament not available"}), 400
    existing = TournamentPlayer.query.filter_by(tournament_id=tid, user_id=current_user.id).first()
    if existing:
        return jsonify({"error": "Already joined"}), 400
    count = TournamentPlayer.query.filter_by(tournament_id=tid).count()
    if count >= t.max_players:
        return jsonify({"error": "Tournament full"}), 400
    tp = TournamentPlayer(tournament_id=tid, user_id=current_user.id, seed=count)
    db.session.add(tp)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/user/settings", methods=["POST"])
@login_required
def api_user_settings():
    data = request.json
    if "board_theme" in data:
        current_user.board_theme = data["board_theme"]
    if "piece_set" in data:
        current_user.piece_set = data["piece_set"]
    if "sound_enabled" in data:
        current_user.sound_enabled = data["sound_enabled"]
    if "zen_mode" in data:
        current_user.zen_mode = data["zen_mode"]
    db.session.commit()
    return jsonify({"success": True})


# ============== SOCKETIO EVENTS ==============

@socketio.on("create_game")
def handle_create_game(data):
    sid = request.sid
    username = session.get("username", "Anonymous")
    rating = data.get("rating", 1200)
    time_control = data.get("time_control", 600)
    game_type = data.get("game_type", "live")
    user_id = current_user.id if current_user.is_authenticated else None
    game_id = uuid.uuid4().hex[:6]
    game = ChessGame(game_id, time_control=time_control, game_type=game_type)
    game.add_player(sid, username, user_id, rating)
    games[game_id] = game
    join_room(game_id)
    emit("game_created", {"game_id": game_id, "color": "white", "state": game.get_state()})
    emit("lobby_update", list_games(), broadcast=True)

@socketio.on("create_ai_game")
def handle_create_ai_game(data):
    sid = request.sid
    username = session.get("username", "Anonymous")
    rating = data.get("rating", 1200)
    difficulty = data.get("difficulty", "intermediate")
    time_control = data.get("time_control", 600)
    user_id = current_user.id if current_user.is_authenticated else None
    game_id = uuid.uuid4().hex[:6]
    game = ChessGame(game_id, time_control=time_control)
    game.setup_ai(sid, username, user_id, rating, difficulty, time_control=time_control)
    games[game_id] = game
    join_room(game_id)
    emit("ai_game_started", {"game_id": game_id, "color": "white", "state": game.get_state()})
    emit("lobby_update", list_games(), broadcast=True)

@socketio.on("find_match")
def handle_find_match(data):
    sid = request.sid
    username = session.get("username", "Anonymous")
    rating = data.get("rating", 1200)
    time_control = data.get("time_control", 600)
    if sid in waiting_players:
        return
    for wsid, wdata in list(waiting_players.items()):
        if wsid != sid:
            game_id = uuid.uuid4().hex[:6]
            tc = min(wdata.get("time_control", 600), time_control)
            game = ChessGame(game_id, time_control=tc)
            w_user_id = wdata.get("user_id")
            u_user_id = current_user.id if current_user.is_authenticated else None
            game.add_player(wsid, wdata["name"], w_user_id, wdata.get("rating", 1200))
            game.add_player(sid, username, u_user_id, rating)
            games[game_id] = game
            join_room(game_id, sid=wsid)
            join_room(game_id, sid=sid)
            del waiting_players[wsid]
            socketio.emit("match_found", {"game_id": game_id, "color": "white", "state": game.get_state()}, to=wsid)
            emit("match_found", {"game_id": game_id, "color": "black", "state": game.get_state()})
            return
    waiting_players[sid] = {"name": username, "rating": rating, "time_control": time_control, "user_id": current_user.id if current_user.is_authenticated else None}
    emit("searching", {"message": "Looking for an opponent..."})

@socketio.on("cancel_search")
def handle_cancel_search():
    sid = request.sid
    if sid in waiting_players:
        del waiting_players[sid]

@socketio.on("join_game")
def handle_join_game(data):
    sid = request.sid
    username = session.get("username", "Anonymous")
    rating = data.get("rating", 1200)
    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        emit("error", {"message": "Game not found"})
        return
    if game.status != "waiting":
        emit("error", {"message": "Game already started or finished"})
        return
    color = game.add_player(sid, username, current_user.id if current_user.is_authenticated else None, rating)
    if not color:
        emit("error", {"message": "Game is full"})
        return
    join_room(game_id)
    state = game.get_state()
    emit("game_joined", {"color": color, "state": state})
    socketio.emit("opponent_joined", {"state": state}, to=game_id)
    emit("lobby_update", list_games(), broadcast=True)

@socketio.on("make_move")
def handle_make_move(data):
    sid = request.sid
    game_id = data.get("game_id")
    move_uci = data.get("move")
    game = games.get(game_id)
    if not game:
        emit("error", {"message": "Game not found"})
        return
    result = game.make_move(sid, move_uci)
    if "error" in result:
        emit("move_error", {"message": result["error"]})
        return
    socketio.emit("move_made", {
        "move": result["san"],
        "uci": move_uci,
        "state": game.get_state(),
    }, to=game_id)
    if game.is_ai and game.status == "active" and game.board.turn == chess.BLACK:
        threading.Thread(target=compute_ai_move, args=(game_id,), daemon=True).start()

def compute_ai_move(game_id):
    game = games.get(game_id)
    if not game or not game.is_ai:
        return
    socketio.emit("ai_thinking", {}, to=game_id)
    depth = SimpleChessAI.DEPTH_MAP.get(game.ai_difficulty, 2)
    time.sleep(0.3 + depth * 0.3)
    ai = SimpleChessAI(difficulty=game.ai_difficulty)
    move = ai.get_best_move(game.board)
    if move is None or game.status != "active":
        return
    result = game.make_ai_move(move.uci())
    if "error" in result:
        return
    socketio.emit("move_made", {
        "move": result["san"],
        "uci": move.uci(),
        "state": game.get_state(),
    }, to=game_id)

@socketio.on("get_legal_moves")
def handle_get_legal_moves(data):
    game_id = data.get("game_id")
    square = data.get("square")
    game = games.get(game_id)
    if not game:
        return
    board = game.board
    try:
        square_idx = chess.parse_square(square)
    except:
        return
    legal_moves = []
    for move in board.legal_moves:
        if move.from_square == square_idx:
            legal_moves.append({
                "from": square,
                "to": chess.square_name(move.to_square),
                "promotion": move.promotion,
            })
    emit("legal_moves", {"moves": legal_moves})

@socketio.on("resign")
def handle_resign(data):
    sid = request.sid
    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        return
    color = game.players.get(sid)
    if not color:
        return
    winner = "black" if color == "white" else "white"
    game.status = "finished"
    game.result_reason = f"{winner} wins by resignation"
    _save_game_result(game)
    socketio.emit("game_over", {
        "result": game.result_reason,
        "winner": winner,
        "state": game.get_state(),
    }, to=game_id)

@socketio.on("offer_draw")
def handle_offer_draw(data):
    sid = request.sid
    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        return
    if game.is_ai:
        return
    if game.draw_offered_by:
        emit("error", {"message": "Draw already offered"})
        return
    game.draw_offered_by = sid
    target_sid = game.black_sid if game.players.get(sid) == "white" else game.white_sid
    if target_sid:
        socketio.emit("draw_offered", {}, to=target_sid)

@socketio.on("accept_draw")
def handle_accept_draw(data):
    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        return
    game.status = "finished"
    game.result_reason = "draw by agreement"
    _save_game_result(game)
    socketio.emit("game_over", {
        "result": game.result_reason,
        "winner": None,
        "state": game.get_state(),
    }, to=game_id)

@socketio.on("decline_draw")
def handle_decline_draw(data):
    sid = request.sid
    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        return
    game.draw_offered_by = None
    target_sid = game.black_sid if game.players.get(sid) == "white" else game.white_sid
    if target_sid:
        socketio.emit("draw_declined", {}, to=target_sid)

@socketio.on("request_rematch")
def handle_rematch(data):
    sid = request.sid
    old_game_id = data.get("game_id")
    old_game = games.get(old_game_id)
    if not old_game:
        return
    my_color = old_game.players.get(sid)
    my_rating = old_game.white_rating if my_color == "white" else old_game.black_rating
    opponent_sid = old_game.black_sid if my_color == "white" else old_game.white_sid
    opponent_rating = old_game.black_rating if my_color == "white" else old_game.white_rating
    game_id = uuid.uuid4().hex[:6]
    time_control = old_game.time_control
    game = ChessGame(game_id, time_control=time_control)
    if old_game.is_ai:
        game.setup_ai(sid, old_game.white_name, old_game.white_id, my_rating, old_game.ai_difficulty, time_control=time_control)
    else:
        game.add_player(sid, old_game.players.get(sid, "Player"), current_user.id if current_user.is_authenticated else None, my_rating)
        if opponent_sid:
            opp_user_id = old_game.white_id if my_color == "white" else old_game.black_id
            game.add_player(opponent_sid, old_game.players.get(opponent_sid, "Player"), opp_user_id, opponent_rating)
    games[game_id] = game
    join_room(game_id, sid=sid)
    if opponent_sid and not old_game.is_ai:
        join_room(game_id, sid=opponent_sid)
        socketio.emit("rematch_started", {"game_id": game_id, "color": "black", "state": game.get_state()}, to=opponent_sid)
    emit("rematch_started", {"game_id": game_id, "color": "white", "state": game.get_state()})

@socketio.on("send_chat")
def handle_chat(data):
    sid = request.sid
    game_id = data.get("game_id")
    message = data.get("message", "").strip()
    if not message or not game_id:
        return
    game = games.get(game_id)
    if not game or sid not in game.players:
        return
    username = session.get("username", "Anonymous")
    if current_user.is_authenticated:
        msg = ChatMessage(game_id=game_id, user_id=current_user.id, message=message)
        db.session.add(msg)
        db.session.commit()
    socketio.emit("chat_message", {"username": username, "message": message}, to=game_id)

@socketio.on("get_chat_history")
def handle_chat_history(data):
    game_id = data.get("game_id")
    if not game_id:
        return
    messages = ChatMessage.query.filter_by(game_id=game_id).order_by(ChatMessage.timestamp).limit(50).all()
    result = []
    for m in messages:
        u = db.session.get(User, m.user_id)
        result.append({"username": u.username if u else "Unknown", "message": m.message})
    emit("chat_history", result)

@socketio.on("connect")
def handle_connect():
    pass

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    if sid in waiting_players:
        del waiting_players[sid]
    for game_id, game in list(games.items()):
        if sid in game.players:
            if game.status == "active" and not game.is_ai:
                game.status = "finished"
                game.result_reason = "Opponent disconnected"
                _save_game_result(game)
                opponent_sid = game.black_sid if game.players[sid] == "white" else game.white_sid
                if opponent_sid:
                    socketio.emit("opponent_disconnected", {"state": game.get_state()}, to=opponent_sid)
            break
    emit("lobby_update", list_games(), broadcast=True)


def _save_game_result(game):
    w_rating_after = game.white_rating_before
    b_rating_after = game.black_rating_before
    if game.white_id and game.black_id:
        w_user = db.session.get(User, game.white_id)
        b_user = db.session.get(User, game.black_id)
        if w_user and b_user:
            result = game.result_reason or ""
            if "wins" in result:
                if result.startswith("white"):
                    update_ratings(w_user, b_user)
                    w_user.wins += 1
                    b_user.losses += 1
                    w_user.streak = max(w_user.streak, 0) + 1
                    b_user.streak = min(b_user.streak, 0) - 1
                else:
                    update_ratings(b_user, w_user)
                    b_user.wins += 1
                    w_user.losses += 1
                    b_user.streak = max(b_user.streak, 0) + 1
                    w_user.streak = min(w_user.streak, 0) - 1
                w_user.max_streak = max(w_user.max_streak, w_user.streak)
                b_user.max_streak = max(b_user.max_streak, b_user.streak)
            elif "draw" in result:
                update_ratings(w_user, b_user, draw=True)
                w_user.draws += 1
                b_user.draws += 1
                w_user.streak = 0
                b_user.streak = 0
            w_rating_after = w_user.rating
            b_rating_after = b_user.rating
    try:
        record = GameRecord(
            game_id=game.id,
            white_id=game.white_id,
            black_id=game.black_id,
            white_name=game.white_name,
            black_name=game.black_name,
            result=game.result_reason or "",
            winner=game.result_reason.split(" wins")[0] if game.result_reason and "wins" in game.result_reason else None,
            termination=game.result_reason or "",
            time_control=game.time_control,
            rated=bool(game.white_id and game.black_id),
            game_type=game.game_type,
            fen=game.board.fen(),
            moves_list=json.dumps(game.move_ucis),
            white_rating_before=game.white_rating_before,
            black_rating_before=game.black_rating_before,
            white_rating_after=w_rating_after,
            black_rating_after=b_rating_after,
        )
        db.session.add(record)
        db.session.commit()
    except Exception as e:
        print("Error saving game:", e)
        db.session.rollback()


def list_games():
    return [
        {"id": g.id, "white": g.white_name, "status": g.status, "players": sum(1 for p in g.players)}
        for g in games.values() if g.status == "waiting"
    ]


with app.app_context():
    db.create_all()
    create_default_puzzles()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True, allow_unsafe_werkzeug=True)
