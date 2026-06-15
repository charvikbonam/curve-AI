from flask import Flask, render_template, request, jsonify, session
from groq import Groq
import os
import uuid
import json
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize Groq client
client = Groq()

# File to store all conversations
CONVERSATIONS_FILE = "conversations.json"

def load_all_conversations():
    """Load all conversations from file"""
    try:
        with open(CONVERSATIONS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_all_conversations(conversations):
    """Save all conversations to file"""
    with open(CONVERSATIONS_FILE, 'w') as f:
        json.dump(conversations, f, indent=2)

def get_or_create_user_id():
    """Get or create a user ID stored in session"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

def get_conversation_title(messages):
    """Generate a title from the first user message"""
    for msg in messages:
        if msg['role'] == 'user':
            title = msg['content'][:50]
            if len(msg['content']) > 50:
                title += "..."
            return title
    return "New Chat"

@app.route('/')
def index():
    user_id = get_or_create_user_id()
    return render_template('index.html')

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    user_id = get_or_create_user_id()
    all_conversations = load_all_conversations()
    
    if user_id not in all_conversations:
        all_conversations[user_id] = {}
    
    # Format conversations for sidebar
    conversations_list = []
    for conv_id, conv_data in all_conversations[user_id].items():
        conversations_list.append({
            'id': conv_id,
            'title': conv_data.get('title', 'New Chat'),
            'created_at': conv_data.get('created_at', ''),
            'updated_at': conv_data.get('updated_at', ''),
            'message_count': len(conv_data.get('messages', []))
        })
    
    # Sort by updated_at (newest first)
    conversations_list.sort(key=lambda x: x['updated_at'], reverse=True)
    
    return jsonify({'conversations': conversations_list})

@app.route('/api/conversation/<conv_id>', methods=['GET'])
def get_conversation(conv_id):
    user_id = get_or_create_user_id()
    all_conversations = load_all_conversations()
    
    if user_id in all_conversations and conv_id in all_conversations[user_id]:
        return jsonify({
            'messages': all_conversations[user_id][conv_id].get('messages', []),
            'title': all_conversations[user_id][conv_id].get('title', 'New Chat')
        })
    
    return jsonify({'messages': [], 'title': 'New Chat'})

@app.route('/api/conversation', methods=['POST'])
def create_conversation():
    user_id = get_or_create_user_id()
    all_conversations = load_all_conversations()
    
    if user_id not in all_conversations:
        all_conversations[user_id] = {}
    
    conv_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    all_conversations[user_id][conv_id] = {
        'id': conv_id,
        'title': 'New Chat',
        'messages': [],
        'created_at': now,
        'updated_at': now
    }
    
    save_all_conversations(all_conversations)
    
    return jsonify({
        'id': conv_id,
        'title': 'New Chat',
        'created_at': now
    })

@app.route('/api/conversation/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    user_id = get_or_create_user_id()
    all_conversations = load_all_conversations()
    
    if user_id in all_conversations and conv_id in all_conversations[user_id]:
        del all_conversations[user_id][conv_id]
        save_all_conversations(all_conversations)
        return jsonify({'status': 'deleted'})
    
    return jsonify({'error': 'Conversation not found'}), 404

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_id = get_or_create_user_id()
    conv_id = data.get('conversation_id')
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    # Load conversations
    all_conversations = load_all_conversations()
    
    if user_id not in all_conversations:
        all_conversations[user_id] = {}
    
    # Create new conversation if needed
    if not conv_id or conv_id not in all_conversations[user_id]:
        conv_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        all_conversations[user_id][conv_id] = {
            'id': conv_id,
            'title': 'New Chat',
            'messages': [],
            'created_at': now,
            'updated_at': now
        }
    
    # Get conversation
    conversation = all_conversations[user_id][conv_id]
    messages = conversation.get('messages', [])
    
    # Add user message
    messages.append({"role": "user", "content": user_message})
    
    try:
        # Get response from Groq
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1024,
        )
        
        ai_response = chat_completion.choices[0].message.content
        
        # Add AI response
        messages.append({"role": "assistant", "content": ai_response})
        
        # Update conversation
        conversation['messages'] = messages
        conversation['updated_at'] = datetime.now().isoformat()
        
        # Set title if this is the first message
        if conversation['title'] == 'New Chat' and len(messages) >= 2:
            conversation['title'] = get_conversation_title(messages)
        
        # Save
        all_conversations[user_id][conv_id] = conversation
        save_all_conversations(all_conversations)
        
        return jsonify({
            'response': ai_response,
            'conversation_id': conv_id,
            'title': conversation['title']
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clear', methods=['POST'])
def clear_conversation():
    data = request.json
    user_id = get_or_create_user_id()
    conv_id = data.get('conversation_id')
    
    if conv_id:
        all_conversations = load_all_conversations()
        if user_id in all_conversations and conv_id in all_conversations[user_id]:
            all_conversations[user_id][conv_id]['messages'] = []
            all_conversations[user_id][conv_id]['updated_at'] = datetime.now().isoformat()
            save_all_conversations(all_conversations)
    
    return jsonify({'status': 'cleared'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
