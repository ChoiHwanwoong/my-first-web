from flask import Flask, render_template, request, jsonify, session, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_woongstagram_app'
DB_PATH = 'comments.db'

# 업로드 폴더 설정
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 사용자 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT,
            email TEXT,
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
            image_url TEXT,
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

    # 4. 좋아요 기록 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            UNIQUE(post_id, username)
        )
    ''')

    # 5. 스토리 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            desc TEXT NOT NULL,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/profile')
def profile_page():
    return render_template('profile.html')

# --- 🔐 Auth APIs ---
@app.route('/api/me', methods=['GET'])
def get_me():
    if 'username' in session:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT username, name, email FROM users WHERE username = ?', (session['username'],))
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({
                'logged_in': True,
                'username': row[0],
                'name': row[1] or row[0],
                'email': row[2] or ''
            })
    return jsonify({'logged_in': False})

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username', '').strip()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not username or not password or not email:
        return jsonify({'status': 'error', 'message': '필수 항목을 모두 입력해 주세요.'}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, name, email, password) VALUES (?, ?, ?, ?)', 
                       (username, name or username, email, password))
        conn.commit()
        conn.close()
        session['username'] = username
        session['name'] = name or username
        return jsonify({'status': 'success', 'username': username})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': '이미 사용 중인 아이디입니다.'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username, name FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session['username'] = user[0]
        session['name'] = user[1] or user[0]
        return jsonify({'status': 'success', 'username': user[0]})
    return jsonify({'status': 'error', 'message': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 400

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'success'})

# --- 📁 파일 업로드 API ---
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': '파일이 선택되지 않았습니다.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '선택된 파일이 없습니다.'}), 400

    if file:
        filename = secure_filename(file.filename)
        # 파일명 중복 방지 (사용자명 접두사)
        save_filename = f"{session['username']}_{int(os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0)}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], save_filename)
        file.save(filepath)
        image_url = f"/static/uploads/{save_filename}"
        return jsonify({'status': 'success', 'image_url': image_url})

# --- 📸 Story APIs ---
@app.route('/api/stories', methods=['GET'])
def get_stories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, title, desc, image_url FROM stories ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    stories = [{'id': r[0], 'username': r[1], 'title': r[2], 'desc': r[3], 'image_url': r[4]} for r in rows]
    return jsonify({'status': 'success', 'stories': stories})

@app.route('/api/stories', methods=['POST'])
def create_story():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    data = request.json
    title = data.get('title', '').strip()
    desc = data.get('desc', '').strip()
    image_url = data.get('image_url', '').strip()

    if not title:
        return jsonify({'status': 'error', 'message': '제목을 입력해 주세요.'}), 400

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO stories (username, title, desc, image_url) VALUES (?, ?, ?, ?)', 
                   (username, title, desc, image_url))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

# --- 📝 Post APIs ---
@app.route('/api/posts', methods=['GET'])
def get_posts():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, title, content, image_url, likes FROM posts ORDER BY id DESC')
    rows = cursor.fetchall()

    user = session.get('username')
    posts = []
    for r in rows:
        post_id = r[0]
        liked = False
        if user:
            cursor.execute('SELECT 1 FROM post_likes WHERE post_id = ? AND username = ?', (post_id, user))
            liked = bool(cursor.fetchone())

        posts.append({
            'id': post_id,
            'username': r[1],
            'title': r[2],
            'content': r[3],
            'image_url': r[4],
            'likes': r[5],
            'is_liked': liked
        })
    conn.close()
    return jsonify({'status': 'success', 'posts': posts})

@app.route('/api/my-posts', methods=['GET'])
def get_my_posts():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, content, image_url, likes FROM posts WHERE username = ? ORDER BY id DESC', (username,))
    rows = cursor.fetchall()
    conn.close()

    posts = [{'id': r[0], 'title': r[1], 'content': r[2], 'image_url': r[3], 'likes': r[4]} for r in rows]
    return jsonify({'status': 'success', 'posts': posts})

@app.route('/api/posts', methods=['POST'])
def create_post():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    image_url = data.get('image_url', '').strip()

    if not title or not content:
        return jsonify({'status': 'error', 'message': '제목과 내용을 모두 입력해주세요.'}), 400

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO posts (username, title, content, image_url) VALUES (?, ?, ?, ?)', 
                   (username, title, content, image_url))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
def toggle_like(post_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 1 FROM post_likes WHERE post_id = ? AND username = ?', (post_id, username))
    liked = cursor.fetchone()

    if liked:
        cursor.execute('DELETE FROM post_likes WHERE post_id = ? AND username = ?', (post_id, username))
        cursor.execute('UPDATE posts SET likes = likes - 1 WHERE id = ? AND likes > 0', (post_id,))
        is_liked = False
    else:
        cursor.execute('INSERT INTO post_likes (post_id, username) VALUES (?, ?)', (post_id, username))
        cursor.execute('UPDATE posts SET likes = likes + 1 WHERE id = ?', (post_id,))
        is_liked = True

    conn.commit()
    cursor.execute('SELECT likes FROM posts WHERE id = ?', (post_id,))
    new_likes = cursor.fetchone()[0]
    conn.close()

    return jsonify({'status': 'success', 'is_liked': is_liked, 'likes': new_likes})

# --- 💬 Comment APIs ---
@app.route('/api/comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, content FROM comments WHERE post_id = ? ORDER BY id ASC', (post_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'status': 'success', 'comments': [{'id': r[0], 'username': r[1], 'content': r[2]} for r in rows]})

@app.route('/api/comments', methods=['POST'])
def add_comment():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    data = request.json
    post_id = data.get('post_id')
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'status': 'error', 'message': '댓글 내용을 입력해 주세요.'}), 400

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO comments (post_id, username, content) VALUES (?, ?, ?)', (post_id, username, content))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM comments WHERE id = ?', (comment_id,))
    row = cursor.fetchone()

    if not row or row[0] != session['username']:
        conn.close()
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    cursor.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)