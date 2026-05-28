from ..config import BASE_URL

class MinerUEndpoints:
    """集中存放各类 API 接口地址"""
    
    @staticmethod
    def get_batch_upload_urls():
        """获取批量上传链接"""
        return f"{BASE_URL}/file-urls/batch"

    @staticmethod
    def get_batch_results(batch_id):
        """获取批量解析任务的结果"""
        return f"{BASE_URL}/extract-results/batch/{batch_id}"

    # 如果未来需要接入 Agent 轻量解析 API，可在这里继续扩充：
    # @staticmethod
    # def get_agent_parse_url():
    #     return f"https://mineru.net/api/v1/agent/parse/url"
