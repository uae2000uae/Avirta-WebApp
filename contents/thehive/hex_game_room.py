import random
import unicodedata
import difflib
from typing import List, Optional, Dict, Any, Tuple

from questionmanagement.categories_questions.question_uploader import QuestionUploader
from questionmanagement.question_bank import question_bank, increment_use_count


def _norm(s: Any) -> str:
    """Unicode-aware normalization for robust matching.

    - Converts to string
    - NFKD normalize and strip combining marks (Arabic diacritics, etc.)
    - Case-fold
    - Remove whitespace and punctuation/symbols for loose comparison
    """
    try:
        text = str(s)
    except Exception:
        return ""
    # Normalize unicode and remove combining marks (e.g., Arabic diacritics)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    text = text.strip().casefold()
    # Remove spaces, punctuation, and symbols for tolerant matching
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch.isalnum():
            cleaned.append(ch)
        elif cat.startswith('L') or cat == 'Nd':
            cleaned.append(ch)
        # else drop (punctuation, symbols, spaces)
    return ''.join(cleaned)


class HexGameRoom:
    """Two-team hexagonal board game (5x5 cells) with multiple-choice questions.

    Rules:
    - Two teams compete. Each cell has a point value and holds a question.
    - Selecting a cell reveals a random multiple-choice question that matches allowed point values.
    - If answered correctly, the cell is colored for the answering team and locked.
    - If answered incorrectly, the cell resets to neutral state and a new random question will be used next time.
    - Questions will not repeat across already-answered cells.
    """

    def __init__(self, room_id: str, name: str, team_a: str, team_b: str,
                 point_values: Optional[List[int]] = None,
                 allowed_question_types: Optional[List[str]] = None):
        self.room_id = room_id
        self.name = name
        self.team_a = team_a
        self.team_b = team_b
        self.teams = [team_a, team_b]
        self.team_colors = {
            team_a: "#1f77b4",  # blue
            team_b: "#d62728",  # red
        }
        self.point_values = sorted(point_values or [100, 200, 300, 400, 500])
        # Only multiple_choice questions are allowed for Hex game.
        self.allowed_question_types = ["multiple_choice"]

        # 5x5 hex grid; store cells as list of dicts for simplicity
        # Each cell: {
        #   'id': index,
        #   'points': int,
        #   'state': 'neutral' | team_a | team_b,
        #   'question': Optional[Dict],  # currently loaded question
        #   'asked': bool,               # whether currently showing a question
        # }
        self.grid: List[Dict[str, Any]] = []
        self.answered_question_ids: set[str] = set()
        self.current_cell_index: Optional[int] = None
        self.current_team_turn: str = self.team_a
        self.available_questions_cache: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'room_id': self.room_id,
            'name': self.name,
            'team_a': self.team_a,
            'team_b': self.team_b,
            'team_colors': self.team_colors,
            'point_values': self.point_values,
            'grid': self.grid,
            'current_cell_index': self.current_cell_index,
            'current_team_turn': self.current_team_turn,
            'winner': self.find_winner(),
        }

    # Board and questions
    def create_board(self, question_uploader: QuestionUploader) -> Tuple[bool, bool, Dict[str, Any]]:
        """Create a 5x5 board with random point values chosen from selected set.
        Returns: (success, enough_questions, error_details)
        """
        self.grid = []
        # Load available text questions matching allowed point values
        all_questions = self._get_filtered_questions(question_uploader)
        if len(all_questions) < 25:
            return False, False, {
                'overall_message': f'Not enough multiple-choice questions to create a 5x5 board. Found {len(all_questions)}, need 25.'
            }
        # Initialize cells with random point values from selection
        for idx in range(25):
            self.grid.append({
                'id': idx,
                'points': random.choice(self.point_values),
                'state': 'neutral',
                'question': None,
                'asked': False,
            })
        # Pre-shuffle available pool for variety
        random.shuffle(all_questions)
        self.available_questions_cache = all_questions
        return True, True, {}

    def _get_filtered_questions(self, question_uploader: QuestionUploader) -> List[Dict[str, Any]]:
        questions: List[Dict[str, Any]] = []
        # question_uploader stores JSON files under contents/questions. Iterate loaded questions.
        # question_uploader.load_questions() should have been called by route before create_board.
        storage = getattr(question_uploader, 'questions', {})
        for _qid, q in storage.items():
            # Accept only multiple-choice questions
            if q.get('type') not in self.allowed_question_types:
                continue
            # Points filter (support various key names: 'points' or 'score')
            pts = q.get('points') or q.get('score') or q.get('value')
            if not isinstance(pts, int):
                try:
                    pts = int(pts)
                except Exception:
                    continue
            if pts not in self.point_values:
                continue
            # Exclude ones already used
            if q.get('id') in self.answered_question_ids:
                continue
            # Ensure options and correct answer exist
            options = q.get('options') or []
            correct_answer = q.get('correct_answer') or q.get('answer')
            if not options or not correct_answer:
                continue
            # Normalize
            qnorm = {
                'id': q.get('id'),
                'question': q.get('question') or q.get('text') or q.get('prompt'),
                'correct_answer': correct_answer,
                'options': options,
                'points': pts,
                'category': q.get('category') or q.get('category_id'),
                'type': 'multiple_choice'
            }
            if qnorm['question'] and qnorm['correct_answer'] and qnorm['options']:
                questions.append(qnorm)
        return questions

    # Gameplay
    def select_cell(self, cell_index: int, question_uploader: QuestionUploader) -> Dict[str, Any]:
        if cell_index < 0 or cell_index >= len(self.grid):
            return {'success': False, 'message': 'Invalid cell index'}
        cell = self.grid[cell_index]
        winner = self.find_winner()
        if winner:
            return {'success': False, 'message': f"{winner['team']} has already won this game.", 'winner': winner}
        if cell['state'] in (self.team_a, self.team_b):
            return {'success': False, 'message': 'Cell already claimed'}
        # If cell has no question or was asked previously and reset, pick a new one matching its points
        question = self._pick_random_question_for_points(question_uploader, cell['points'])
        if not question:
            return {'success': False, 'message': 'No available question for this point value'}
        # Randomize options order for multiple-choice questions before sending to client
        try:
            if isinstance(question, dict) and (question.get('type') == 'multiple_choice' or ('options' in question and question.get('correct_answer'))):
                opts = list(question.get('options') or [])
                if len(opts) > 1:
                    random.shuffle(opts)
                    question['options'] = opts
        except Exception:
            # Do not fail selection if shuffling fails
            pass

        cell['question'] = question
        cell['asked'] = True
        self.current_cell_index = cell_index
        # Remember it for the rest of this game (older saved rooms lack the set).
        if getattr(self, 'asked_question_ids', None) is None:
            self.asked_question_ids = set()
        if question.get('id'):
            self.asked_question_ids.add(question['id'])
        # Note: use_count is updated upon answering to reflect actual usage, not just reveal.
        return {'success': True, 'cell': cell}

    def _pick_random_question_for_points(self, question_uploader: QuestionUploader, points: int) -> Optional[Dict[str, Any]]:
        """Pick a question with the smallest global use_count for the given points.
        Randomize among the minimal-count tier to avoid repeats.
        """
        pool = [q for q in self._get_filtered_questions(question_uploader) if q['points'] == points]
        if not pool:
            return None
        # Never repeat a question within a game, unless this point value has
        # truly run out (then any question is better than an empty cell).
        asked = getattr(self, 'asked_question_ids', None) or set()
        fresh = [q for q in pool if q.get('id') not in asked]
        if fresh:
            pool = fresh

        def get_use_count(q: Dict[str, Any]) -> int:
            try:
                qb_q = question_bank.questions.get(q.get('id')) if hasattr(question_bank, 'questions') else None
                uc = qb_q.get('use_count', 0) if qb_q else 0
                return int(uc) if isinstance(uc, (int, float, str)) and str(uc).isdigit() else int(uc)
            except Exception:
                # Default to 0 if any error
                try:
                    return int(q.get('use_count', 0))
                except Exception:
                    return 0

        # Find the minimum use_count in the pool
        min_use = None
        for q in pool:
            uc = get_use_count(q)
            if min_use is None or uc < min_use:
                min_use = uc
        if min_use is None:
            return random.choice(pool)
        least_used = [q for q in pool if get_use_count(q) == min_use]
        return random.choice(least_used)

    def submit_answer(self, team_name: str, answer: str) -> Dict[str, Any]:
        if self.current_cell_index is None:
            return {'success': False, 'message': 'No active cell'}
        cell = self.grid[self.current_cell_index]
        q = cell.get('question')
        if not q:
            return {'success': False, 'message': 'No question loaded'}

        # Compute correctness using normalized comparison
        is_correct = self._validate_answer(q, answer)
        correct_answer = q.get('correct_answer')
        options = q.get('options') or []
        # Find index of correct answer in options using robust normalization
        correct_index = -1
        try:
            for i, opt in enumerate(options):
                if _norm(opt) == _norm(correct_answer):
                    correct_index = i
                    break
        except Exception:
            correct_index = -1
        # Fallback: fuzzy match to find the closest option if exact normalized match failed
        if correct_index == -1 and options:
            try:
                target = _norm(correct_answer)
                best_i, best_ratio = -1, 0.0
                for i, opt in enumerate(options):
                    ratio = difflib.SequenceMatcher(None, _norm(opt), target).ratio()
                    if ratio > best_ratio:
                        best_ratio, best_i = ratio, i
                if best_ratio >= 0.6:
                    correct_index = best_i
            except Exception:
                pass

        if is_correct:
            # Update use_count upon answering
            try:
                if q.get('id'):
                    increment_use_count(q['id'])
            except Exception:
                pass
            cell['state'] = team_name
            self.answered_question_ids.add(q['id'])
            cell['asked'] = False
            self.current_cell_index = None
            # Switch turn to the other team after success as well (optional rule)
            self._switch_turn()
            return {
                'success': True,
                'correct': True,
                'cell': cell,
                'correct_answer': correct_answer,
                'correct_index': correct_index,
                'winner': self.find_winner(),
            }
        # Incorrect: reset cell to neutral and clear question
        try:
            if q.get('id'):
                increment_use_count(q['id'])
        except Exception:
            pass
        cell['question'] = None
        cell['asked'] = False
        self.current_cell_index = None
        # Switch turn to the other team after a miss
        self._switch_turn()
        return {
            'success': True,
            'correct': False,
            'cell': cell,
            'correct_answer': correct_answer,
            'correct_index': correct_index,
        }

    def _validate_answer(self, question: Dict[str, Any], answer: str) -> bool:
        """Validate answer with tolerant matching.
        Primary check uses strict normalized equality; fallbacks allow containment and high similarity.
        """
        correct = _norm(question.get('correct_answer', ''))
        user = _norm(answer)
        if correct == user:
            return True
        # Containment tolerance (handles prefixed/suffixed options like "1) Answer")
        if correct and (correct in user or user in correct):
            return True
        # Fuzzy similarity fallback
        try:
            ratio = difflib.SequenceMatcher(None, user, correct).ratio()
            if ratio >= 0.9:
                return True
        except Exception:
            pass
        return False

    def _switch_turn(self):
        self.current_team_turn = self.team_b if self.current_team_turn == self.team_a else self.team_a

    # Winning: Hex-style connection of a team's two board edges.
    # The 5x5 board is drawn as rows of hexes with every odd row shifted right
    # by half a cell ("odd-r" offset), so each cell touches up to six others.
    # Team A (top/bottom edges) wins by linking row 0 to the last row; team B
    # (left/right edges) wins by linking column 0 to the last column.
    SIZE = 5

    def neighbors(self, index: int) -> List[int]:
        n = self.SIZE
        r, c = divmod(index, n)
        if r % 2 == 0:
            deltas = [(0, -1), (0, 1), (-1, -1), (-1, 0), (1, -1), (1, 0)]
        else:
            deltas = [(0, -1), (0, 1), (-1, 0), (-1, 1), (1, 0), (1, 1)]
        out = []
        for dr, dc in deltas:
            rr, cc = r + dr, c + dc
            if 0 <= rr < n and 0 <= cc < n:
                out.append(rr * n + cc)
        return out

    def _connection_path(self, team: str, starts: List[int], is_goal) -> Optional[List[int]]:
        """Shortest chain of `team` cells from any start cell to a goal cell (BFS)."""
        owned = {i for i, cell in enumerate(self.grid) if cell.get('state') == team}
        queue = [i for i in starts if i in owned]
        parent: Dict[int, Optional[int]] = {i: None for i in queue}
        while queue:
            current = queue.pop(0)
            if is_goal(current):
                path = []
                while current is not None:
                    path.append(current)
                    current = parent[current]
                return list(reversed(path))
            for nb in self.neighbors(current):
                if nb in owned and nb not in parent:
                    parent[nb] = current
                    queue.append(nb)
        return None

    def find_winner(self) -> Optional[Dict[str, Any]]:
        """Return {'team', 'color', 'path', 'edges'} once a team links its edges, else None."""
        n = self.SIZE
        if len(self.grid) != n * n:
            return None
        checks = (
            (self.team_a, [c for c in range(n)], lambda i: i // n == n - 1, 'top-bottom'),
            (self.team_b, [r * n for r in range(n)], lambda i: i % n == n - 1, 'left-right'),
        )
        for team, starts, goal, edges in checks:
            path = self._connection_path(team, starts, goal)
            if path:
                return {'team': team, 'color': self.team_colors.get(team), 'path': path, 'edges': edges}
        return None

    def get_board_state(self) -> Dict[str, Any]:
        return {
            'grid': self.grid,
            'current_team_turn': self.current_team_turn,
            'team_colors': self.team_colors,
            'team_a': self.team_a,
            'team_b': self.team_b,
            'winner': self.find_winner(),
        }

    # Lifecycle compatibility with app.py end_game route
    def end_game(self) -> bool:
        """Finalize the Hive game session.

        Provided to satisfy the generic end_game() call in app.py. The Hive game
        does not require special teardown; app.py handles snapshotting and
        cleanup of in-memory/persisted room data. This method is a safe no-op.
        Returns True for compatibility.
        """
        # No internal resources to release for Hive at this time.
        return True
