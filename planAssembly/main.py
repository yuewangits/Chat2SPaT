# Main fuction
from Chat2SPaT import convertChatPlanResToSpatParams

if __name__ == '__main__':
    '''Use LLM outputs as inputs - resStr, to generate SPaT results.
    Example inputs:
    resStr = 
    {
      "result1": {
        "stageStyle": [
          [
            { "NBL": { "split": 21 } },
            { "SBL": { "split": 21 } }
          ],
          [
            { "SBL": { "split": 18 } },
            { "SBT": { "split": 18 } }
          ],
          [
            { "NBT": { "split": 26 } },
            { "SBT": { "split": 26 } }
          ],
          [
            { "EBL": { "split": 17 } },
            { "WBL": { "split": 17 } }
          ],
          [
            { "EBT": { "split": 22 } },
            { "WBT": { "split": 22 } }
          ]
        ]
      },
      "result2": [
        { "NBL": { "phaseOrder": 1, "greenFlash": 3 } },
        { "SBL": { "phaseOrder": 1, "greenFlash": 3, "lateStart": 5 } },
        { "SBL": { "phaseOrder": 2, "greenFlash": 3 } },
        { "SBT": { "phaseOrder": 1, "greenFlash": 3 } },
        { "NBT": { "phaseOrder": 1, "greenFlash": 3 } },
        { "SBT": { "phaseOrder": 2, "greenFlash": 3 } },
        { "EBL": { "phaseOrder": 1, "greenFlash": 3 } },
        { "WBL": { "phaseOrder": 1, "greenFlash": 3, "earlyCutOff": 4 } },
        { "EBT": { "phaseOrder": 1, "greenFlash": 3, "redAmber": 3 } },
        { "WBT": { "phaseOrder": 1, "greenFlash": 3, "redAmber": 3 } }
      ],
      "result3": null
    }
    '''
    
    try:
        resOfChat2SPaT = convertChatPlanResToSpatParams(resStr)
    except:
        resOfChat2SPaT = None
        print("TSC plan cannot be assembled using the inputs. \nPlease check your LLM outputs and use valid inputs.")
