from flask import Flask, render_template, send_from_directory
import redis
from PIL import Image
import io
import os
import threading
from datetime import datetime

app = Flask(__name__)

# Global variable to store the latest image filename
latest_image = None

def listen_to_channel():
    global latest_image
    # Connect to Redis
    r = redis.Redis(host='34.55.93.180', port=6379, db=0)

    # Subscribe to the 'frame_sync' channel
    pubsub = r.pubsub()
    pubsub.subscribe('frame_sync')

    print("Listening for messages on 'frame_sync' channel...")
    
    # Ensure the 'static/frames' directory exists
    if not os.path.exists('static/frames'):
        os.makedirs('static/frames')

    # Listen for messages
    for message in pubsub.listen():
        if message['type'] == 'message':
            try:
                # Decode the message
                decoded_message = message['data'].decode('utf-8')
                
                # Split the message into parts
                parts = decoded_message.split("--AKTAR--")
                if len(parts) == 3:
                    timestamp = parts[0]
                    camera_list = parts[1].split(",")
                    
                    image_data = r.hget(timestamp, camera_list[0])
                    
                    if image_data:
                        # Convert the byte data to an image
                        image = Image.open(io.BytesIO(image_data))
                        
                        # Construct a filename using the timestamp
                        filename = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                        filepath = f"static/frames/{filename}"
                        
                        # Save the image
                        image.save(filepath)
                        print(f"Image saved as: {filepath}")
                        
                        # Update the latest image filename
                        latest_image = filename
                    
            except Exception as e:
                print(f"Error processing message: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_latest_image')
def get_latest_image():
    return {'image': latest_image} if latest_image else {'image': None}

if __name__ == '__main__':
    # Start the Redis listener in a separate thread
    redis_thread = threading.Thread(target=listen_to_channel, daemon=True)
    redis_thread.start()
    print("Redis listener started")
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5003)
