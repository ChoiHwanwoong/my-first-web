from flask import Flask, render_template, request, jsonify, session
import psycopg2
import psycopg2.extras
import os
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_woongstagram_app'

DEFAULT_DB_URL = "postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz.region.aws.neon.tech/neondb?sslmode=require"
DATABASE_URL = os.environ.get('DATABASE_URL', DEFAULT_DB_URL)

cloudinary.config(secure=True)

NEWS_CACHE = {
    'updated_at': None,
    'articles': []
}

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(100),
            email VARCHAR(255),
            password VARCHAR(255) NOT NULL,
            profile_img TEXT DEFAULT ''
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL,
            title VARCHAR(255) DEFAULT '',
            content TEXT NOT NULL,
            image_url TEXT,
            likes INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            post_id INT NOT NULL,
            username VARCHAR(100) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_likes (
            id SERIAL PRIMARY KEY,
            post_id INT NOT NULL,
            username VARCHAR(100) NOT NULL,
            UNIQUE(post_id, username)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stories (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL,
            title VARCHAR(255) DEFAULT '',
            desc_text TEXT NOT NULL,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS story_views (
            id SERIAL PRIMARY KEY,
            story_id INT NOT NULL,
            username VARCHAR(100) NOT NULL,
            UNIQUE(story_id, username)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS follows (
            id SERIAL PRIMARY KEY,
            follower VARCHAR(100) NOT NULL,
            following VARCHAR(100) NOT NULL,
            UNIQUE(follower, following)
        );
    ''')
    conn.commit()
    cursor.close()
    conn.close()

init_db()

def is_admin():
    return session.get('username') == 'admin'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/profile')
@app.route('/profile/<username>')
def profile_page(username=None):
    return render_template('profile.html', target_username=username)

@app.route('/admin')
def admin_page():
    if not is_admin():
        return "<script>alert('관리자 권한이 필요합니다.'); location.href='/';</script>"
    return render_template('admin.html')

# --- 👑 Admin APIs ---
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    if not is_admin():
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM users;')
    user_cnt = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM posts;')
    post_cnt = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM comments;')
    comment_cnt = cursor.fetchone()[0]

    cutoff_time = datetime.now() - timedelta(hours=24)
    cursor.execute('SELECT COUNT(*) FROM stories WHERE created_at >= %s;', (cutoff_time,))
    story_cnt = cursor.fetchone()[0]

    cursor.close()
    conn.close()
    return jsonify({
        'status': 'success',
        'stats': {
            'users': user_cnt,
            'posts': post_cnt,
            'comments': comment_cnt,
            'stories': story_cnt
        }
    })

@app.route('/api/admin/users', methods=['GET'])
def get_admin_users():
    if not is_admin():
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT id, username, email, profile_img FROM users ORDER BY id DESC;')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    users = [{'id': r['id'], 'username': r['username'], 'email': r['email'], 'profile_img': r['profile_img'] or ''} for r in rows]
    return jsonify({'status': 'success', 'users': users})

@app.route('/api/admin/users/<username>', methods=['DELETE'])
def delete_admin_user(username):
    if not is_admin():
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    if username == 'admin':
        return jsonify({'status': 'error', 'message': '관리자 계정은 삭제할 수 없습니다.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM posts WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM comments WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM stories WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM follows WHERE follower = %s OR following = %s;', (username, username))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/admin/posts/<int:post_id>', methods=['DELETE'])
def delete_admin_post(post_id):
    if not is_admin():
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM posts WHERE id = %s;', (post_id,))
    cursor.execute('DELETE FROM comments WHERE post_id = %s;', (post_id,))
    cursor.execute('DELETE FROM post_likes WHERE post_id = %s;', (post_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/admin/stories/<int:story_id>', methods=['DELETE'])
def delete_admin_story(story_id):
    if not is_admin():
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM stories WHERE id = %s;', (story_id,))
    cursor.execute('DELETE FROM story_views WHERE story_id = %s;', (story_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

# --- 📰 1시간 주기 뉴스 API ---
@app.route('/api/news', methods=['GET'])
def get_hot_news():
    now = datetime.now()
    
    if NEWS_CACHE['updated_at'] and (now - NEWS_CACHE['updated_at']) < timedelta(hours=1):
        return jsonify({'status': 'success', 'articles': NEWS_CACHE['articles'], 'cached': True})

    articles = []
    try:
        rss_url = 'https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko'
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('./channel/item')[:5]:
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                articles.append({'title': title, 'link': link})
    except Exception as e:
        print("RSS Error:", e)

    NEWS_CACHE['updated_at'] = now
    NEWS_CACHE['articles'] = articles

    return jsonify({'status': 'success', 'articles': articles, 'cached': False})

# --- 🔐 Auth & User APIs ---
@app.route('/api/me', methods=['GET'])
def get_me():
    if 'username' in session:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute('SELECT username, name, email, profile_img FROM users WHERE username = %s;', (session['username'],))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return jsonify({
                'logged_in': True,
                'username': row['username'],
                'name': row['username'],
                'email': row['email'] or '',
                'profile_img': row['profile_img'] or '',
                'is_admin': row['username'] == 'admin'
            })
    return jsonify({'logged_in': False, 'is_admin': False})

@app.route('/api/users/<username>', methods=['GET'])
def get_user_profile(username):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT username, name, email, profile_img FROM users WHERE username = %s;', (username,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '사용자를 찾을 수 없습니다.'}), 404

    cursor.execute('SELECT COUNT(*) FROM follows WHERE following = %s;', (username,))
    follower_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM follows WHERE follower = %s;', (username,))
    following_count = cursor.fetchone()[0]

    is_following = False
    me = session.get('username')
    if me:
        cursor.execute('SELECT 1 FROM follows WHERE follower = %s AND following = %s;', (me, username))
        is_following = bool(cursor.fetchone())

    cursor.close()
    conn.close()

    return jsonify({
        'status': 'success',
        'user': {
            'username': row['username'],
            'name': row['username'],
            'email': row['email'] or '',
            'profile_img': row['profile_img'] or '',
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
        try:
            upload_result = cloudinary.uploader.upload(file, folder="woongstagram/profiles")
            image_url = upload_result.get('secure_url')

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET profile_img = %s WHERE username = %s;', (image_url, session['username']))
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({'status': 'success', 'profile_img': image_url})
        except Exception as e:
            return jsonify({'status': 'error', 'message': f'이미지 업로드 실패: {str(e)}'}), 500

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not username or not password or not email:
        return jsonify({'status': 'error', 'message': '필수 항목을 모두 입력해 주세요.'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (username, name, email, password) VALUES (%s, %s, %s, %s);', 
                       (username, username, email, password))
        conn.commit()
        cursor.close()
        conn.close()
        session['username'] = username
        session['name'] = username
        return jsonify({'status': 'success', 'username': username})
    except psycopg2.IntegrityError:
        return jsonify({'status': 'error', 'message': '이미 사용 중인 아이디입니다.'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT username, name FROM users WHERE username = %s AND password = %s;', (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user:
        session['username'] = user['username']
        session['name'] = user['username']
        return jsonify({'status': 'success', 'username': user['username']})
    return jsonify({'status': 'error', 'message': '아이디 또는 비밀번호가 올바르지 않습니다.'}), 400

@app.route('/api/find-id', methods=['POST'])
def find_id():
    data = request.json
    email = data.get('email', '').strip()

    if not email:
        return jsonify({'status': 'error', 'message': '이메일 주소를 입력해 주세요.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT username FROM users WHERE email = %s;', (email,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if rows:
        usernames = [r['username'] for r in rows]
        return jsonify({'status': 'success', 'usernames': usernames})
    return jsonify({'status': 'error', 'message': '해당 이메일로 가입된 계정을 찾을 수 없습니다.'}), 404

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    new_password = data.get('new_password', '').strip()

    if not username or not email or not new_password:
        return jsonify({'status': 'error', 'message': '모든 필수 항목을 입력해 주세요.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = %s AND email = %s;', (username, email))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '아이디와 이메일 정보가 일치하는 계정이 없습니다.'}), 404

    cursor.execute('UPDATE users SET password = %s WHERE username = %s AND email = %s;', (new_password, username, email))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/change-password', methods=['POST'])
def change_password():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    data = request.json
    current_password = data.get('current_password', '').strip()
    new_password = data.get('new_password', '').strip()

    if not current_password or not new_password:
        return jsonify({'status': 'error', 'message': '현재 비밀번호와 새 비밀번호를 모두 입력해 주세요.'}), 400

    username = session['username']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = %s AND password = %s;', (username, current_password))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '현재 비밀번호가 올바르지 않습니다.'}), 400

    cursor.execute('UPDATE users SET password = %s WHERE username = %s;', (new_password, username))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/delete-account', methods=['POST'])
def delete_account():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    username = session['username']
    if username == 'admin':
        return jsonify({'status': 'error', 'message': '관리자 계정은 삭제할 수 없습니다.'}), 400

    data = request.json
    password = data.get('password', '').strip()

    if not password:
        return jsonify({'status': 'error', 'message': '비밀번호를 입력해 주세요.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = %s AND password = %s;', (username, password))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '비밀번호가 올바르지 않습니다.'}), 400

    cursor.execute('DELETE FROM users WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM posts WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM comments WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM stories WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM follows WHERE follower = %s OR following = %s;', (username, username))
    cursor.execute('DELETE FROM post_likes WHERE username = %s;', (username,))
    cursor.execute('DELETE FROM story_views WHERE username = %s;', (username,))
    conn.commit()

    cursor.close()
    conn.close()
    session.clear()

    return jsonify({'status': 'success'})

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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT 1 FROM follows WHERE follower = %s AND following = %s;', (me, target_username))
    row = cursor.fetchone()

    if row:
        cursor.execute('DELETE FROM follows WHERE follower = %s AND following = %s;', (me, target_username))
        is_following = False
    else:
        cursor.execute('INSERT INTO follows (follower, following) VALUES (%s, %s);', (me, target_username))
        is_following = True

    conn.commit()

    cursor.execute('SELECT COUNT(*) FROM follows WHERE following = %s;', (target_username,))
    follower_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    return jsonify({'status': 'success', 'is_following': is_following, 'follower_count': follower_count})

@app.route('/api/users/<username>/followers', methods=['GET'])
def get_followers(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT follower FROM follows WHERE following = %s;', (username,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'status': 'success', 'users': [r[0] for r in rows]})

@app.route('/api/users/<username>/following', methods=['GET'])
def get_following(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT following FROM follows WHERE follower = %s;', (username,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({'status': 'success', 'users': [r[0] for r in rows]})

# ☁️ 업로드 API
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    if 'files' in request.files:
        files = request.files.getlist('files')
        image_urls = []
        for file in files:
            if file and file.filename != '':
                try:
                    upload_result = cloudinary.uploader.upload(file, folder="woongstagram/posts")
                    image_urls.append(upload_result.get('secure_url'))
                except Exception as e:
                    return jsonify({'status': 'error', 'message': f'클라우드 업로드 실패: {str(e)}'}), 500
        return jsonify({'status': 'success', 'image_urls': image_urls, 'image_url': image_urls[0] if image_urls else ''})

    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '':
            try:
                upload_result = cloudinary.uploader.upload(file, folder="woongstagram/posts")
                image_url = upload_result.get('secure_url')
                return jsonify({'status': 'success', 'image_url': image_url, 'image_urls': [image_url]})
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'클라우드 업로드 실패: {str(e)}'}), 500

    return jsonify({'status': 'error', 'message': '선택된 파일이 없습니다.'}), 400

# --- 🤖 Recommendation API ---
@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    current_user = session.get('username')
    if current_user == 'admin':
        return jsonify({'status': 'success', 'recommendations': []})

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    recommendations = []

    if current_user:
        query = '''
            SELECT pl2.username, COUNT(*) as common_likes
            FROM post_likes pl1
            JOIN post_likes pl2 ON pl1.post_id = pl2.post_id
            WHERE pl1.username = %s AND pl2.username != %s AND pl2.username != 'admin'
            GROUP BY pl2.username
            ORDER BY common_likes DESC
            LIMIT 3;
        '''
        cursor.execute(query, (current_user, current_user))
        similar_users = cursor.fetchall()

        for u in similar_users:
            cursor.execute('SELECT profile_img FROM users WHERE username = %s;', (u['username'],))
            p_img = cursor.fetchone()
            recommendations.append({
                'username': u['username'],
                'reason': f"{current_user}님과 취향이 비슷함",
                'profile_img': p_img['profile_img'] if p_img and p_img['profile_img'] else ''
            })

    if len(recommendations) < 3:
        exclude_users = [current_user, 'admin'] if current_user else ['admin']
        exclude_users.extend([r['username'] for r in recommendations])
        
        placeholders = ', '.join(['%s'] * len(exclude_users)) if exclude_users else "''"
        query_general = f'''
            SELECT username, name, profile_img FROM users 
            WHERE username NOT IN ({placeholders})
            LIMIT %s;
        '''
        params = list(exclude_users) + [3 - len(recommendations)]
        cursor.execute(query_general, params)
        general_users = cursor.fetchall()

        for u in general_users:
            recommendations.append({
                'username': u['username'],
                'reason': 'Woongstagram 추천 회원',
                'profile_img': u['profile_img'] or ''
            })

    cursor.close()
    conn.close()
    return jsonify({'status': 'success', 'recommendations': recommendations})

# --- 📸 Story APIs ---
@app.route('/api/stories', methods=['GET'])
def get_stories():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cutoff_time = datetime.now() - timedelta(hours=24)
    cursor.execute('DELETE FROM stories WHERE created_at < %s;', (cutoff_time,))
    conn.commit()

    cursor.execute('SELECT s.id, s.username, s.title, s.desc_text, s.image_url, s.created_at, u.profile_img FROM stories s LEFT JOIN users u ON s.username = u.username ORDER BY s.id DESC;')
    rows = cursor.fetchall()

    user = session.get('username')
    stories = []
    for r in rows:
        story_id = r['id']
        is_viewed = False
        if user:
            cursor.execute('SELECT 1 FROM story_views WHERE story_id = %s AND username = %s;', (story_id, user))
            is_viewed = bool(cursor.fetchone())

        stories.append({
            'id': story_id,
            'username': r['username'],
            'title': r['title'] or '',
            'desc': r['desc_text'],
            'image_url': r['image_url'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else '',
            'profile_img': r['profile_img'] or '',
            'is_viewed': is_viewed
        })

    cursor.close()
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

    if not desc and not image_url:
        return jsonify({'status': 'error', 'message': '스토리 내용이나 사진을 등록해 주세요.'}), 400

    username = session['username']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO stories (username, title, desc_text, image_url) VALUES (%s, %s, %s, %s);', 
                   (username, title, desc, image_url))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/stories/<int:story_id>', methods=['DELETE'])
def delete_user_story(story_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM stories WHERE id = %s;', (story_id,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '스토리를 찾을 수 없습니다.'}), 404

    if not is_admin() and row[0] != session['username']:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '삭제 권한이 없습니다.'}), 403

    cursor.execute('DELETE FROM stories WHERE id = %s;', (story_id,))
    cursor.execute('DELETE FROM story_views WHERE story_id = %s;', (story_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/stories/<int:story_id>/view', methods=['POST'])
def mark_story_viewed(story_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    username = session['username']
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('INSERT INTO story_views (story_id, username) VALUES (%s, %s);', (story_id, username))
        conn.commit()
    except psycopg2.IntegrityError:
        pass

    cursor.close()
    conn.close()
    return jsonify({'status': 'success'})

# --- 📝 Post APIs (제목 없는 형태 지원) ---
@app.route('/api/posts', methods=['GET'])
def get_posts():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT p.id, p.username, p.title, p.content, p.image_url, p.likes, p.created_at, u.profile_img FROM posts p LEFT JOIN users u ON p.username = u.username ORDER BY p.id DESC;')
    rows = cursor.fetchall()

    user = session.get('username')
    posts = []
    for r in rows:
        post_id = r['id']
        liked = False
        if user:
            cursor.execute('SELECT 1 FROM post_likes WHERE post_id = %s AND username = %s;', (post_id, user))
            liked = bool(cursor.fetchone())

        raw_img = r['image_url'] or ''
        image_urls = []
        if raw_img:
            if raw_img.startswith('['):
                try:
                    image_urls = json.loads(raw_img)
                except:
                    image_urls = [raw_img]
            else:
                image_urls = [raw_img]

        posts.append({
            'id': post_id,
            'username': r['username'],
            'title': r['title'] or '',
            'content': r['content'],
            'image_url': image_urls[0] if image_urls else '',
            'image_urls': image_urls,
            'likes': r['likes'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else '',
            'profile_img': r['profile_img'] or '',
            'is_liked': liked
        })
    cursor.close()
    conn.close()
    return jsonify({'status': 'success', 'posts': posts})

@app.route('/api/posts/<int:post_id>', methods=['GET'])
def get_single_post(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT p.id, p.username, p.title, p.content, p.image_url, p.likes, p.created_at, u.profile_img FROM posts p LEFT JOIN users u ON p.username = u.username WHERE p.id = %s;', (post_id,))
    r = cursor.fetchone()

    if not r:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '게시글을 찾을 수 없습니다.'}), 404

    user = session.get('username')
    liked = False
    if user:
        cursor.execute('SELECT 1 FROM post_likes WHERE post_id = %s AND username = %s;', (post_id, user))
        liked = bool(cursor.fetchone())

    cursor.close()
    conn.close()

    raw_img = r['image_url'] or ''
    image_urls = []
    if raw_img:
        if raw_img.startswith('['):
            try:
                image_urls = json.loads(raw_img)
            except:
                image_urls = [raw_img]
        else:
            image_urls = [raw_img]

    return jsonify({
        'status': 'success',
        'post': {
            'id': r['id'],
            'username': r['username'],
            'title': r['title'] or '',
            'content': r['content'],
            'image_url': image_urls[0] if image_urls else '',
            'image_urls': image_urls,
            'likes': r['likes'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else '',
            'profile_img': r['profile_img'] or '',
            'is_liked': liked
        }
    })

@app.route('/api/posts/<int:post_id>', methods=['PUT'])
def update_user_post(post_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'status': 'error', 'message': '내용을 입력해 주세요.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM posts WHERE id = %s;', (post_id,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '게시글을 찾을 수 없습니다.'}), 404

    if not is_admin() and row[0] != session['username']:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '수정 권한이 없습니다.'}), 403

    cursor.execute('UPDATE posts SET title = %s, content = %s WHERE id = %s;', (title, content, post_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/posts/<int:post_id>', methods=['DELETE'])
def delete_user_post(post_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM posts WHERE id = %s;', (post_id,))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '게시글을 찾을 수 없습니다.'}), 404

    if not is_admin() and row[0] != session['username']:
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '삭제 권한이 없습니다.'}), 403

    cursor.execute('DELETE FROM posts WHERE id = %s;', (post_id,))
    cursor.execute('DELETE FROM comments WHERE post_id = %s;', (post_id,))
    cursor.execute('DELETE FROM post_likes WHERE post_id = %s;', (post_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/posts/user/<username>', methods=['GET'])
def get_user_posts(username):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT id, title, content, image_url, likes, created_at FROM posts WHERE username = %s ORDER BY id DESC;', (username,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    posts = []
    for r in rows:
        raw_img = r['image_url'] or ''
        image_urls = []
        if raw_img:
            if raw_img.startswith('['):
                try:
                    image_urls = json.loads(raw_img)
                except:
                    image_urls = [raw_img]
            else:
                image_urls = [raw_img]

        posts.append({
            'id': r['id'],
            'title': r['title'] or '',
            'content': r['content'],
            'image_url': image_urls[0] if image_urls else '',
            'image_urls': image_urls,
            'likes': r['likes'],
            'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else ''
        })

    return jsonify({'status': 'success', 'posts': posts})

@app.route('/api/posts', methods=['POST'])
def create_post():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    data = request.json
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    image_urls = data.get('image_urls', [])

    if not image_urls and data.get('image_url'):
        image_urls = [data.get('image_url')]

    if not content:
        return jsonify({'status': 'error', 'message': '내용을 입력해 주세요.'}), 400

    username = session['username']
    image_url_db = json.dumps(image_urls) if image_urls else ''

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO posts (username, title, content, image_url) VALUES (%s, %s, %s, %s);', 
                   (username, title, content, image_url_db))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
def toggle_like(post_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    username = session['username']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT 1 FROM post_likes WHERE post_id = %s AND username = %s;', (post_id, username))
    liked = cursor.fetchone()

    if liked:
        cursor.execute('DELETE FROM post_likes WHERE post_id = %s AND username = %s;', (post_id, username))
        cursor.execute('UPDATE posts SET likes = likes - 1 WHERE id = %s AND likes > 0;', (post_id,))
        is_liked = False
    else:
        cursor.execute('INSERT INTO post_likes (post_id, username) VALUES (%s, %s);', (post_id, username))
        cursor.execute('UPDATE posts SET likes = likes + 1 WHERE id = %s;', (post_id,))
        is_liked = True

    conn.commit()
    cursor.execute('SELECT likes FROM posts WHERE id = %s;', (post_id,))
    new_likes = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    return jsonify({'status': 'success', 'is_liked': is_liked, 'likes': new_likes})

# --- 💬 Comment APIs ---
@app.route('/api/comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute('SELECT c.id, c.username, c.content, c.created_at, u.profile_img FROM comments c LEFT JOIN users u ON c.username = u.username WHERE c.post_id = %s ORDER BY c.id ASC;', (post_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    comments = [{
        'id': r['id'],
        'username': r['username'],
        'content': r['content'],
        'created_at': r['created_at'].strftime('%Y-%m-%d %H:%M:%S') if r['created_at'] else '',
        'profile_img': r['profile_img'] or ''
    } for r in rows]

    return jsonify({'status': 'success', 'comments': comments})

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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO comments (post_id, username, content) VALUES (%s, %s, %s);', 
                   (post_id, username, content))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': '로그인이 필요합니다.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM comments WHERE id = %s;', (comment_id,))
    row = cursor.fetchone()

    if not is_admin() and (not row or row[0] != session['username']):
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '권한이 없습니다.'}), 403

    cursor.execute('DELETE FROM comments WHERE id = %s;', (comment_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)