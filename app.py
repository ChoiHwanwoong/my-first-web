from flask import Flask, render_template, request, jsonify, session
import sqlite3
import os
import feedparser
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_woongstagram_app'
DB_PATH = 'comments.db'

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- 📰 뉴스 캐싱 변수 (6시간 주기) ---
NEWS_CACHE = {
    'updated_at': None,
    'articles': []
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT,
            email TEXT,
            password TEXT NOT NULL,
            profile_img TEXT DEFAULT ''
        )
    ''')

    try:
        cursor.execute('ALTER TABLE users ADD COLUMN profile_img TEXT DEFAULT ""')
    except sqlite3.OperationalError:
        pass
    
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            UNIQUE(post_id, username)
        )
    ''')

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS story_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            UNIQUE(story_id, username)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower TEXT NOT NULL,
            following TEXT NOT NULL,
            UNIQUE(follower, following)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/profile')
@app.route('/profile/<username>')
def profile_page(username=None):
    return render_template('profile.html', target_username=username)

# --- 📰 6시간 주기 뉴스 API ---
@app.route('/api/news', methods=['GET'])
def get_hot_news():
    now = datetime.now()
    
    # 6시간 캐시 검증
    if NEWS_CACHE['updated_at'] and (now - NEWS_CACHE['updated_at']) < timedelta(hours=6):
        return jsonify({'status': 'success', 'articles': NEWS_CACHE['articles'], 'cached': True})

    # RSS 피드를 통한 뉴스 수집 (다음/구글 뉴스 핫이슈)
    rss_url = 'https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko'
    feed = feedparser.parse(rss_url)

    articles = []
    for entry in feed.entries[:5]: # 상위 5개 주요 뉴스
        articles.append({
            'title': entry.title,
            'link': entry.link,
            'pubDate': entry.get('published', '')
        })

    # 캐시 저장
    NEWS_CACHE['updated_at'] = now
    NEWS_CACHE['articles'] = articles

    return jsonify({'status': 'success', 'articles': articles, 'cached': False})

# --- 🔐 Auth & User APIs ---
@app.route('/api/me', methods=['GET'])
def get_me():
    if 'username' in session:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT username, name, email, profile_img FROM users WHERE username = ?', (session['username'],))
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({
                'logged_in': True,
                'username': row[0],
                'name': row[1] or row[0],
                'email': row[2] or '',
                'profile_img': row[3] or ''
            })
    return jsonify({'logged_in': False})

@app.route('/api/users/<username>', methods=['GET'])
def get_user_profile(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username, name, email, profile_img FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': '사용자를 찾을 수 없습니다.'}), 404

    cursor.execute('SELECT COUNT(*) FROM follows WHERE following = ?', (username,))
    follower_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM follows WHERE follower = ?', (username,))
    following_count = cursor.fetchone()[0]

    is_following = False
    me = session.get('username')
    if me:
        cursor.execute('SELECT 1 FROM follows WHERE follower = ? AND following = ?', (me, username))
        is_following = bool(cursor.fetchone())

    conn.close()

    return jsonify({
        'status': 'success',
        'user': {
            'username': row[0],
            'name': row[1] or row[0],
            'email': row[2] or '',
            'profile_img': row[3] or '',
            'follower_count': follower_count,
            'following_count': following_count,
            'is_following': is_following
        }
    })

@app.route('/api/profile-image', methods=['POST'])
def update_profile_image():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': '파일이 없습니다.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '선택된 파일이 없습니다.'}), 400

    if file:
        filename = secure_filename(file.filename)
        save_filename = f"profile_{session['username']}_{int(datetime.now().timestamp())}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], save_filename)
        file.save(filepath)
        image_url = f"/static/uploads/{save_filename}"

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET profile_img = ? WHERE username = ?', (image_url, session['username']))
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'profile_img': image_url})

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

# --- 🤝 Follow APIs ---
@app.route('/api/follow/<target_username>', methods=['POST'])
def toggle_follow(target_username):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    me = session['username']
    if me == target_username:
        return jsonify({'status': 'error', 'message': '자기 자신은 팔로우할 수 없습니다.'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT 1 FROM follows WHERE follower = ? AND following = ?', (me, target_username))
    row = cursor.fetchone()

    if row:
        cursor.execute('DELETE FROM follows WHERE follower = ? AND following = ?', (me, target_username))
        is_following = False
    else:
        cursor.execute('INSERT INTO follows (follower, following) VALUES (?, ?)', (me, target_username))
        is_following = True

    conn.commit()

    cursor.execute('SELECT COUNT(*) FROM follows WHERE following = ?', (target_username,))
    follower_count = cursor.fetchone()[0]
    conn.close()

    return jsonify({'status': 'success', 'is_following': is_following, 'follower_count': follower_count})

@app.route('/api/users/<username>/followers', methods=['GET'])
def get_followers(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT follower FROM follows WHERE following = ?', (username,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'status': 'success', 'users': [r[0] for r in rows]})

@app.route('/api/users/<username>/following', methods=['GET'])
def get_following(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT following FROM follows WHERE follower = ?', (username,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'status': 'success', 'users': [r[0] for r in rows]})

# --- 📁 Upload API ---
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
        save_filename = f"{session['username']}_{int(datetime.now().timestamp())}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], save_filename)
        file.save(filepath)
        image_url = f"/static/uploads/{save_filename}"
        return jsonify({'status': 'success', 'image_url': image_url})

# --- 🤖 Recommendation API ---
@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    current_user = session.get('username')
    recommendations = []

    if current_user:
        query = '''
            SELECT pl2.username, COUNT(*) as common_likes
            FROM post_likes pl1
            JOIN post_likes pl2 ON pl1.post_id = pl2.post_id
            WHERE pl1.username = ? AND pl2.username != ?
            GROUP BY pl2.username
            ORDER BY common_likes DESC
            LIMIT 3
        '''
        cursor.execute(query, (current_user, current_user))
        similar_users = cursor.fetchall()

        for u in similar_users:
            cursor.execute('SELECT profile_img FROM users WHERE username = ?', (u[0],))
            p_img = cursor.fetchone()
            recommendations.append({
                'username': u[0],
                'reason': f"{current_user}님과 취향이 비슷함",
                'profile_img': p_img[0] if p_img else ''
            })

    if len(recommendations) < 3:
        exclude_users = [current_user] if current_user else []
        exclude_users.extend([r['username'] for r in recommendations])
        
        placeholders = ', '.join(['?'] * len(exclude_users)) if exclude_users else "''"
        query_general = f'''
            SELECT username, name, profile_img FROM users 
            WHERE username NOT IN ({placeholders})
            LIMIT ?
        '''
        params = list(exclude_users) + [3 - len(recommendations)]
        cursor.execute(query_general, params)
        general_users = cursor.fetchall()

        for u in general_users:
            recommendations.append({
                'username': u[0],
                'reason': 'Woongstagram 추천 회원',
                'profile_img': u[2] or ''
            })

    conn.close()
    return jsonify({'status': 'success', 'recommendations': recommendations})

# --- 📸 Story APIs ---
@app.route('/api/stories', methods=['GET'])
def get_stories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cutoff_time = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('DELETE FROM stories WHERE created_at < ?', (cutoff_time,))
    conn.commit()

    cursor.execute('SELECT s.id, s.username, s.title, s.desc, s.image_url, s.created_at, u.profile_img FROM stories s LEFT JOIN users u ON s.username = u.username ORDER BY s.id DESC')
    rows = cursor.fetchall()

    user = session.get('username')
    stories = []
    for r in rows:
        story_id = r[0]
        is_viewed = False
        if user:
            cursor.execute('SELECT 1 FROM story_views WHERE story_id = ? AND username = ?', (story_id, user))
            is_viewed = bool(cursor.fetchone())

        stories.append({
            'id': story_id,
            'username': r[1],
            'title': r[2],
            'desc': r[3],
            'image_url': r[4],
            'created_at': r[5],
            'profile_img': r[6] or '',
            'is_viewed': is_viewed
        })

    conn.close()
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
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO stories (username, title, desc, image_url, created_at) VALUES (?, ?, ?, ?, ?)', 
                   (username, title, desc, image_url, now_str))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/stories/<int:story_id>/view', methods=['POST'])
def mark_story_viewed(story_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    username = session['username']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('INSERT INTO story_views (story_id, username) VALUES (?, ?)', (story_id, username))
        conn.commit()
    except sqlite3.IntegrityError:
        pass

    conn.close()
    return jsonify({'status': 'success'})

# --- 📝 Post APIs ---
@app.route('/api/posts', methods=['GET'])
def get_posts():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT p.id, p.username, p.title, p.content, p.image_url, p.likes, p.created_at, u.profile_img FROM posts p LEFT JOIN users u ON p.username = u.username ORDER BY p.id DESC')
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
            'created_at': r[6],
            'profile_img': r[7] or '',
            'is_liked': liked
        })
    conn.close()
    return jsonify({'status': 'success', 'posts': posts})

@app.route('/api/posts/<int:post_id>', methods=['GET'])
def get_single_post(post_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT p.id, p.username, p.title, p.content, p.image_url, p.likes, p.created_at, u.profile_img FROM posts p LEFT JOIN users u ON p.username = u.username WHERE p.id = ?', (post_id,))
    r = cursor.fetchone()

    if not r:
        conn.close()
        return jsonify({'status': 'error', 'message': '게시글을 찾을 수 없습니다.'}), 404

    user = session.get('username')
    liked = False
    if user:
        cursor.execute('SELECT 1 FROM post_likes WHERE post_id = ? AND username = ?', (post_id, user))
        liked = bool(cursor.fetchone())

    conn.close()

    return jsonify({
        'status': 'success',
        'post': {
            'id': r[0],
            'username': r[1],
            'title': r[2],
            'content': r[3],
            'image_url': r[4],
            'likes': r[5],
            'created_at': r[6],
            'profile_img': r[7] or '',
            'is_liked': liked
        }
    })

@app.route('/api/posts/user/<username>', methods=['GET'])
def get_user_posts(username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, content, image_url, likes, created_at FROM posts WHERE username = ? ORDER BY id DESC', (username,))
    rows = cursor.fetchall()
    conn.close()

    posts = [{'id': r[0], 'title': r[1], 'content': r[2], 'image_url': r[3], 'likes': r[4], 'created_at': r[5]} for r in rows]
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
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO posts (username, title, content, image_url, created_at) VALUES (?, ?, ?, ?, ?)', 
                   (username, title, content, image_url, now_str))
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
    cursor.execute('SELECT c.id, c.username, c.content, c.created_at, u.profile_img FROM comments c LEFT JOIN users u ON c.username = u.username WHERE c.post_id = ? ORDER BY c.id ASC', (post_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify({'status': 'success', 'comments': [{'id': r[0], 'username': r[1], 'content': r[2], 'created_at': r[3], 'profile_img': r[4] or ''} for r in rows]})

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
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO comments (post_id, username, content, created_at) VALUES (?, ?, ?, ?)', 
                   (post_id, username, content, now_str))
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