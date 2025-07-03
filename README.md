# Chat2SPaT

# Introduction
  Chat2SPaT is an LLM-powered tool that converts traffic engineers' descriptions on traffic signal control plans to exact signal plan and timing results.
  With a curated prompt, Chat2SPaT leverages LLMs' capability of understanding users' plan descriptions and reformulate the plan as a combination of phase sequence and phase attribute results in json format. Based on LLM outputs, python scripts are designed to locate phases in a cycle, address nuances of traffic signal control, and finally assemble the complete traffic signal control plan. Within a chat, the pipeline could be utilized iteratively to conduct further plan editing.

# Run the Project
  Chat2SPaT consists of three steps. First, feed the prompt to your LLM (either a locally deployed LLM or via an LLM service API) to instruct it to understand TSC domain specific knowledge and formatting requirements of the outputs. Based on our experiments, ChatGPT-4o is recommended for English users and Qwen2.5-72B-Instruct is recommended for Chinese users. The accuracy may drop using models smaller than 32B.
  Second, provide your TSC plan descriptions. Once the LLM sees your plan descriptions, it will output the results in the specified json format. Along with the plan descriptions, it is recommended to tell LLMs whether you are inputting a new plan or you would like to modify the current plan, with some helpful words such as "A new plan", "further", etc.
  Third, run the python scripts of plan assembly using LLM outputs. There is no special requirement for the environment or python packages to run the scripts. The program would generate a plan dictionary object, recording the information of each phase, along with second-by-second traffic signal color code, and warning messages (if the plan is invalid). A signal times table plot is also generated, for users to visualize and confirm the plan. If you need to conduct further modifications, provide additional descriptions and go through step 2 and 3 interatively. 

# Plan Description Dataset
  A bilingual test dataset with over 300 plan descriptions is created for an extensive evaluation of Chat2SPaT's performance, covering common plan schemes and description styles. The 'ground truth' traffic signal color codes of the TSC plan for each description is provided in the dataset as well. You may refer to the descriptions in the dataset as example inputs for Chat2SPaT. You are also welcome to contribute more cases in the dataset to help improve the model.

# Credits
  Chat2SPaT is built for a research project by the ITS Lab of R&D Center at Zhejiang Dahua Technology Company Ltd., Hangzhou 310053, China. We would like to express our gratitude to Zhenliang Ma from KTH and Guijing Huang from Alibaba Cloud, for their help in LLM technologies and experimental design.
