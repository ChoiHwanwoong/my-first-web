from flask import Flask, render_template, request, jsonify
import sqlite3
import os

app = Flask(__name__)
DB_PATH = 'comments.db'

# 데이터베이스 초기화 (테이블 생성)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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

# 1. 댓글 조회 API
@app.route('/api/comments/<int:post_id>', methods=['GET'])
def get_comments(post_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, content FROM comments WHERE post_id = ? ORDER BY id ASC', (post_id,))
    rows = cursor.fetchall()
    conn.close()
    
    comments = [{'id': row[0], 'username': row[1], 'content': row[2]} for row in rows]
    return jsonify({'status': 'success', 'comments': comments})

# 2. 댓글 추가 API
@app.route('/api/comments', methods=['POST'])
def add_comment():
    data = request.json
    post_id = data.get('post_id')
    username = data.get('username', 'woong_dev')
    content = data.get('content')

    if not content:
        return jsonify({'status': 'error', 'message': '내용을 입력해주세요.'}), 400

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

# 3. 댓글 삭제 API
@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True)