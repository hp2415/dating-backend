from app.modules.media.storage import normalize_stored_media_url, object_public_url


def test_aliyun_public_url_is_virtual_hosted():
    url = object_public_url(
        "https://oss-cn-beijing.aliyuncs.com",
        "spark-media",
        "post/2026/a.jpg",
    )
    assert url == "https://spark-media.oss-cn-beijing.aliyuncs.com/post/2026/a.jpg"


def test_aliyun_public_url_does_not_double_bucket_host():
    url = object_public_url(
        "https://spark-media.oss-cn-beijing.aliyuncs.com",
        "spark-media",
        "post/2026/a.jpg",
    )
    assert url == "https://spark-media.oss-cn-beijing.aliyuncs.com/post/2026/a.jpg"


def test_minio_stays_path_style():
    url = object_public_url("http://minio:9000", "dating", "post/a.jpg")
    assert url == "http://minio:9000/dating/post/a.jpg"


def test_rewrite_stored_path_style_url():
    stored = "https://oss-cn-beijing.aliyuncs.com/spark-media/post/2026/a.jpg"
    assert (
        normalize_stored_media_url(stored, bucket="spark-media")
        == "https://spark-media.oss-cn-beijing.aliyuncs.com/post/2026/a.jpg"
    )


def test_rewrite_doubled_bucket_in_virtual_host():
    stored = "https://spark-media.oss-cn-beijing.aliyuncs.com/spark-media/post/2026/a.jpg"
    assert (
        normalize_stored_media_url(stored, bucket="spark-media")
        == "https://spark-media.oss-cn-beijing.aliyuncs.com/post/2026/a.jpg"
    )


def test_already_virtual_hosted_url_is_unchanged():
    stored = "https://spark-media.oss-cn-beijing.aliyuncs.com/post/2026/a.jpg"
    assert normalize_stored_media_url(stored, bucket="spark-media") == stored
