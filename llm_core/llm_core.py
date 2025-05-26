
import os
print(os.getcwd())

from openai import OpenAI

from utils.utils import base64_encode_image

from utils.log_utils import get_logger


logger = get_logger()


class tingjianLLM:
    def __init__(self):
        # OpenAI and Qwen client setup
        if os.environ.get("API_KEY"):
            self.client = OpenAI(api_key=os.environ["API_KEY"])
            self.OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4")
            
        elif os.getenv('DASHSCOPE_API_KEY'):
            self.client = OpenAI(
                api_key=os.getenv('DASHSCOPE_API_KEY'),
                base_url=os.getenv('DASHSCOPE_BASE_URL'),
            )
            self.DASHSCOPE_MODEL = os.getenv('DASHSCOPE_MODEL', 'gpt-4o-mini')
            logger.info("Qwen client loaded with model: %s", self.DASHSCOPE_MODEL)
        else:
            logger.info("Missing LLM KEY")
            self.client = None
            raise ValueError("Missing LLM KEY")


    # Helper function to generate descriptions using OpenAI
    def openai_get_description_from_image(self, image):
        base64_image = base64_encode_image(image)

        prompt = "Give a short description of the image and where objects are located in the image. Do not mention that this is an image. Do not mention weather or geographical location. Less text is better."

        response = self.client.chat.completions.create(
            model=self.OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                        },
                    ],
                }
            ],
        )
        logger.debug(f"Response: {response}")
        logger.info(f"Response content: {response.choices[0].message.content}")
        return response.choices[0].message.content

    def tongyi_get_description_from_image(self, image_fp, question="请为我描述周围的环境"):
        logger.info("getting description using tongyi qwen")
        base64_image = base64_encode_image(image_fp)

        system_prompt = '''
        你是一个导盲助手, 这是一张来自盲人举起手机拍摄的正前方的照片.照片的左侧是拍摄者的左手方向 , 右侧是拍摄者的右手方向.
        你需要为他描述周围的环境. 请注意,他的眼睛是看不到的.
        使用中文进行回复.避免使用列表、加粗等格式符号,只保留文字
        
        请按照 从近到远,从左向右的顺序进行描述.
        请简明准确语言的描述环境, 描述主要物品的位置.
        如果出现文字,请正确描述文字内容, 不要忽略.
        
        - 你可以使用以下格式描述物体和位置关系:
            "在...的前面"、"在...的后面"、"在...的左边"、"在...的右边"、"在...的上面"、"在...的下面"

        - 如果有如下物品请注意描述不要忽略:
            1. 交通信号灯, 如 ”现在是红灯“
            2. 人行横道线, 如 ”人行横道线在正前面“
            3. 交通站点建筑, 如 ”公交车站在左边“ “前方是地下通道入口”
            4. 地名/位置 指示牌, 如 ”1号出口在右边“ “这里是地铁10号线的入口”
            5. 盲道, 如 ”盲道在右边“
        
        - 如果照片中道路被堵塞, 请你描述道路的情况和周围的环境。帮助用户离开堵塞的地方.
            例如: "前面有一辆车挡住了路, 你可以向左转, 继续前行." "前方有一个大坑, 请小心行走." "前面有一个人挡住了路, 请向右转." "前面有一个台阶, 请小心上下." "前方有一个栏杆,请向右转绕开."
            
        '''

        messages = [
                {"role":"system",
                "content": [
                    {
                        "type": "text",
                        "text": system_prompt
                    }
                ]}
                ,{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}, 
                        },
                        {"type": "text", "text": question},
                    ],
                }
            ]

        response = self.client.chat.completions.create(
            model=self.DASHSCOPE_MODEL,
            messages=messages,
        )
        
        logger.debug(f"Response: {response}")
        logger.info(f"Response content: {response.choices[0].message.content}")
        return response.choices[0].message.content

    def tongyi_get_followup_from_image(self,image_fp, question="请为我描述周围的环境"):
        logger.info(f"getting followup using tongyi qwen, question:{question}")
        base64_image = base64_encode_image(image_fp)

        system_prompt = '''
        你是一个导盲助手. 这是一张来自盲人举起手机拍摄的正前方的照片, 照片的左侧是拍摄者的左手方向 , 右侧是拍摄者的右手方向.
        你需要根据他提供的图片来回答他的问题,请注意,他的眼睛是看不到的.
        使用中文的口语的风格进行回复.避免使用列表、加粗等格式符号, 只保留文字。
        
        '''

        messages = [
                {"role":"system",
                "content": [
                    {
                        "type": "text",
                        "text": system_prompt
                    }
                ]}
                ,{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}, 
                        },
                        {"type": "text", "text": question},
                    ],
                }
            ]

        response = self.client.chat.completions.create(
            model=self.DASHSCOPE_MODEL,
            messages=messages,
        )
        
        logger.debug(f"Response: {response}")
        logger.info(f"Response content: {response.choices[0].message.content}")
        return response.choices[0].message.content


if __name__ == '__main__':
    from dotenv import load_dotenv, find_dotenv
    import argparse
    parser = argparse.ArgumentParser(description="Test the tingjianLLM class.")
    parser.add_argument('--img_fp', type=str, required=True, help='Path to the image file')
    
    args = parser.parse_args()
    img_fp = args.img_fp

    load_dotenv(find_dotenv())

    llm = tingjianLLM()
    # Prompt Testing
    llm.tongyi_get_description_from_image(img_fp)