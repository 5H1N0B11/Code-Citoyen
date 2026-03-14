import sys
try:
    import youtube_transcript_api
    from youtube_transcript_api import YouTubeTranscriptApi
    print(f"Module file: {youtube_transcript_api.__file__}")
    print(f"Dir(YouTubeTranscriptApi): {dir(YouTubeTranscriptApi)}")
    try:
        print(f"Version: {youtube_transcript_api.__version__}")
    except AttributeError:
        print("Version not found in module.")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
