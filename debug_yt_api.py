from youtube_transcript_api import YouTubeTranscriptApi

yt = YouTubeTranscriptApi()
transcript_list = yt.list('NO8cUqaYxOM')

# Get the first transcript (French auto-generated usually)
transcript = None
for t in transcript_list:
    transcript = t
    break

if transcript:
    print("Fetching transcript...")
    raw_data = transcript.fetch()
    print(f"Fetched data type: {type(raw_data)}")
    
    if len(raw_data) > 0:
        item = raw_data[0]
        print(f"First item type: {type(item)}")
        print(f"First item attributes: {dir(item)}")
        
        # Check standard attributes
        try:
            print(f"Text: {item.text}")
            print(f"Start: {item.start}")
            print(f"Duration: {item.duration}")
        except AttributeError:
            print("Could not access standard attributes directly.")
else:
    print("No transcript found to test.")