import boto3

if __name__ == "__main__":
    s3 = boto3.resource("s3")
    s3.Bucket("games-collections")
