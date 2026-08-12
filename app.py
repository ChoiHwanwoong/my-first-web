from flask import Flask, render_template, request, jsonify, session
import sqlite3

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_instagram_app'  # 세션 암호화 키
DB_PATH = 'comments.db'

# 데이터베이스 초기화 (회원, 게시글, 댓글 테이블)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 사용자 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # 2. 게시글 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            likes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. 댓글 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

# --- 🔐 사용자 인증 API ---

# 로그인 상태 확인
@app.route('/api/me', methods=['GET'])
def get_me():
    if 'username' in session:
        return jsonify({'logged_in': True, 'username': session['username']})
    return jsonify({'logged_in': False})

# 회원가입
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'status': 'error', 'message': '아이디와 비밀번호를 모두 입력해주세요.'}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        conn.commit()
        conn.close()
        session['username'] = username
        return jsonify({'status': 'success', 'username': username})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': '이미 존재하는 아이디입니다.'}), 400

# 로그인
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session['username'] = username
        return jsonify({'status': 'success', 'username': username})
    return jsonify({'status': 'error', 'message': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 400

# 로그아웃
@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({'status': 'success'})

# --- 📝 게시글 API ---

# 게시글 목록 조회
@app.route('/api/posts', methods=['GET'])
def get_posts():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, title, content, likes FROM posts ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    posts = [{'id': r[0], 'username': r[1], 'title': r[2], 'content': r[3], 'likes': r[4]} for r in rows]
    return jsonify({'status': 'success', 'posts': posts})

# 게시글 생성 (로그인 필수)
@app.route('/api/posts', methods=['POST'])
def create_post():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요한 기능입니다.'}), 401

    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({'status': 'error', 'message': '제목과 내용을 입력해주세요.'}), 400

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO posts (username, title, content) VALUES (?, ?, ?)', (username, title, content))
    conn.commit()
    post_id = cursor.lastrowid
    conn.close()

    return jsonify({
        'status': 'success',
        'post': {'id': post_id, 'username': username, 'title': title, 'content': content, 'likes': 0}
    })

# --- 💬 댓글 API ---

# 댓글 조회
@app.route('/api/comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, content FROM comments WHERE post_id = ? ORDER BY id ASC', (post_id,))
    rows = cursor.fetchall()
    conn.close()
    
    comments = [{'id': r[0], 'username': r[1], 'content': r[2]} for r in rows]
    return jsonify({'status': 'success', 'comments': comments})

# 댓글 작성 (로그인 필수)
@app.route('/api/comments', methods=['POST'])
def add_comment():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요한 기능입니다.'}), 401

    data = request.json
    post_id = data.get('post_id')
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'status': 'error', 'message': '내용을 입력해주세요.'}), 400

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO comments (post_id, username, content) VALUES (?, ?, ?)', (post_id, username, content))
    conn.commit()
    comment_id = cursor.lastrowid
    conn.close()

    return jsonify({
        'status': 'success',
        'comment': {'id': comment_id, 'username': username, 'content': content}
    })

# 댓글 삭제 (작성자 또는 본인 권한)
@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요한 기능입니다.'}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM comments WHERE id = ?', (comment_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': '댓글을 찾을 수 없습니다.'}), 404

    if row[0] != session['username']:
        conn.close()
        return jsonify({'status': 'error', 'message': '본인의 댓글만 삭제할 수 있습니다.'}), 403

    cursor.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)