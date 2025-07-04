import copy
import json

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

# Function for plan generation using LLM outputs
def convertChatPlanResToSpatParams(resStr, plot=True):
    '''
    Convert json format plan results by LLM to plan scheme object, with plan result validation and visualization.
    
    Parameters:
    resStr(json object as str): json format plan results by LLM, based on user's plan descriptions.
    plot: boolean, whether to make a plot for the plan or not.

    Returns:
    resOfChat2SPaT(dict): The generated plan obj, with plan scheme including phase info and second-by-second traffic light color code.
    Warning msgs are included for plan validation.
    A plot of the traffic color is shown for visualization for users. 
    '''
    # Step 0: Read LLM outputs

    # List of format errors in LLM outputs:
    # Type 0 format error: result1 (or result2) is recorded as a dict instead of list
    # Type 1 format error: no stage or ring label; defaulted as stage
    # Type 2 format error: no nested list in stage or ring structure
    # Type 3 format error: phaseName is recorded for the same movements of two opposing directions such as '南北直行'

    # Read LLM outputs
    res=json.loads(resStr)
    result1, result2, result3 = res["result1"], res["result2"], res["result3"]

    # Deal with Type 0 format error in result 1
    # result1 formatting
    if result1 == None:
        result1 =[]
    if type(result1) == dict:
        result1_formattedAsList = [{k:result1[k]} for k in result1]
        result1 = result1_formattedAsList# [result1]

    # Deal with Type 0 format error in result 2
    if type(result2) == dict: # Type 0 format error is found for result2
        result2_Type0Errorformatted = []
        for phaseName in result2:
            phase = {phaseName: result2[phaseName]}
            result2_Type0Errorformatted.append(phase)        
        result2 = result2_Type0Errorformatted

    # Formatting phase names in result2
    result2 = [{phaseNameFormatting(list(_.keys())[0]): _[list(_.keys())[0]]} for _ in result2]
    # Formatting parentPhase phase names in result2
    for phase in result2:
        phaseName = helper_getSubValueFromPhase('phaseName', phase)
        parentPhaseRecorded = helper_getSubValueFromPhase('parentPhase', phase)
        if parentPhaseRecorded != None and parentPhaseRecorded != 'default':
            phase[phaseName].update({'parentPhase': phaseNameFormatting(parentPhaseRecorded)})

    # Update result2-phaseOrder
    for i in range(len(result2)):
        phase = result2[i]
        phaseName = helper_getSubValueFromPhase('phaseName', phase)
        phaseOrder = sum([helper_getSubValueFromPhase('phaseName', _)==phaseName for _ in result2[:i]]) + 1
        phase[phaseName].update({'phaseOrder': phaseOrder})

    # Replace placeholder for cycleLength in result2
    for phase in result2:
        phaseName = helper_getSubValueFromPhase('phaseName', phase)
        if helper_getSubValueFromPhase('endTime', phase) == 'cycleLength':
            if result3 != None:
                phase[phaseName].update({'endTime': result3})

    # Deal with Type 1 format error in result 1
    result1_Type1Errorformatted = []
    for obj in result1:
        if type(obj) == dict:
            # If an element in the list in result1 is a stageStyle or a ringStyle, there is no Type 1 format error
            if 'stageStyle' in obj or 'ringStyle' in obj:
                result1_Type1Errorformatted.append(obj)
                continue
            # There is Type 1 format error for this element, convert it to a stageStyle object.
            stageList = [{k: obj[k]} for k in obj]
            stageObj = {'stageStyle': [stageList]}
            result1_Type1Errorformatted.append(stageObj)
        else:
            stageObj = {'stageStyle': [obj]}
            result1_Type1Errorformatted.append(stageObj)

    result1 = result1_Type1Errorformatted

    # Deal with Type 3 format error in result 2
    result2_Type3Errorformatted = []

    for phaseRaw in result2:
        phaseNameRaw = helper_getSubValueFromPhase('phaseName', phaseRaw)
        phaseNameSeparatedList = helper_separateCombinedOppositeMovements(phaseNameRaw)
        if len(phaseNameSeparatedList) == 1:
            result2_Type3Errorformatted.append(phaseRaw)
        else: # Type 3 format error in result2 is found
            for phaseName in phaseNameSeparatedList:
                phase = {phaseName: phaseRaw[phaseNameRaw]} 

                # 在result2中搜索该相位（同order）
                flagSeparatedPhaseFound = False
                for i in range(len(result2)):
                    phaseInfoObj = result2[i]
                    if helper_getSubValueFromPhase('phaseName', phaseInfoObj) == phaseName and\
                        helper_getSubValueFromPhase('phaseOrder', phaseInfoObj) == helper_getSubValueFromPhase('phaseOrder', phase):
                        phaseInfoObj[phaseName].update(phase[phaseName])
                        flagSeparatedPhaseFound = True
                        break

                if flagSeparatedPhaseFound == False:

                    order = helper_AssignPhaseOrder(result2, phaseName)
                    phase[phaseName].update({'phaseOrder': order}) # 该拆解相位的order           
                    result2_Type3Errorformatted.append(phase)

    result2 = result2_Type3Errorformatted

    # Step 1: Locate major phases in the cycle, based on stage or ring structure

    # Initialize the final outputs
    resOfChat2SPaT = {'resStr': res}

    # Break down stage or ring structure
    cycleLengthByUser = result3
    cycleLength = cycleLengthByUser if cycleLengthByUser != None else None  # read cycleLength provided by user, if any.
    curStartTime = 0
    planSchemeMajor = []   # Initialize planSchemeMajor as an empty table (list of lists)

    for obj in result1:
        # The object is a stage style
        if 'stageStyle' in obj.keys():
            stageList = obj["stageStyle"]
            if len(stageList) == 0:
                continue
            if type(stageList[0]) != list:  # Type 2 format error
                stageList = [stageList] 
            for stage in stageList:
                maxEndTimeOfStage = -1  # 记录该阶段的最晚的结束时间
                for phaseRaw in stage:
                    phaseNameRaw = helper_getSubValueFromPhase('phaseName', phaseRaw) # get raw phaseName                
                    #phase = {phaseNameFormatting(phaseNameRaw): phase[phaseNameRaw]} # update the phase obj
                    phaseNameFormatted = helper_getSubValueFromPhase('phaseName', phaseRaw) # get standard phaseName
                    phaseNameFormatted = phaseNameFormatting(phaseNameRaw)

                    # Calculate and assign attributes for each phase separated from phaseNameRaw---------------------------------------
                    phaseNameSeparatedList = helper_separateCombinedOppositeMovements(phaseNameFormatted)
                    for phaseName in phaseNameSeparatedList:
                        phase = {phaseName: phaseRaw[phaseNameRaw]} 

                        # 写入该相位的order 
                        order = helper_AssignPhaseOrder(planSchemeMajor, phaseName)
                        phase[phaseName].update({'phaseOrder': order}) # 该相位的order             

                        # grab phaseInfo from result2
                        phaseInfoObj = helper_getPhaseInfo(phaseName, order, result2)
                        #if phaseInfoObj != None:
                        phaseInfoObj = {phaseName: {}} if phaseInfoObj == None else phaseInfoObj
                        phase[phaseName].update(phaseInfoObj[phaseName]) # merge the phase info from result1 and result2

                        # infer the split's startTime, endTime, and split based on the counterparts of greenTime, if needed.
                        helper_textualStartAndEndTime(phase, cycleLength)
                        helper_inferStartAndEndTime(phase)
                        helper_inferSplitAndGreen(phase)
                        startTime = helper_getSubValueFromPhase('startTime', phase)
                        split = helper_getSubValueFromPhase('split', phase)
                        if split == 0 or type(split) != int: # 如果相位时长为0，大概是因为跟随相位被误写到了result1中，忽略这样的相位
                            continue
                        endTime = helper_getSubValueFromPhase('endTime', phase)

                        # Assign start time if missing, as curStartTime
                        if startTime == None:
                            startTime = curStartTime
                            phase[phaseName].update({"startTime": startTime})

                        # 相位时间信息的容错处理
                        # 要求startTime、endTime、split中，至少有两个不为None；否则，忽略该相位
                        if (endTime != None) + (split != None) + (startTime != None) < 2:
                            continue

                        # Calculate split from start and end time of the phase if possible                            
                        if split == None and startTime != None and endTime != None:
                            split = helper_calcSplitFromStartAndEndTime(startTime, endTime) #helper_calcSplitFromGreenTime(phase)

                        # Calculate end time if needed             
                        if endTime == None and split != None: # Use startTime and split
                            endTime = startTime + split
                            endTime = helper_modifyCyclicTimepoint(endTime, cycleLength)
                            phase[phaseName].update({"endTime": endTime})
                        else: # endTime cannot be located. Will throw error?
                            pass

                        # 将完整的该相位的信息写入planSchemeMajor
                        if '全行人' in phaseName:
                            for phaseNameForAllPed in ['北行人', '东行人', '南行人', '西行人']:
                                # 将各方向的行人相位添加到planScheme中
                                phaseForAllPedInPlanScheme = {phaseNameForAllPed: copy.deepcopy(phase[phaseName])}
                                planSchemeMajor.append(phaseForAllPedInPlanScheme)
                                # 在result2中也将全行人相位改为各方向的行人相位
                                phaseForAllPedInResult2 = {phaseNameForAllPed: copy.deepcopy(phaseInfoObj[phaseName])}
                                result2.append(phaseForAllPedInResult2)
                        elif 'ALLPED' in phaseName:
                            for phaseNameForAllPed in ['NORTHPED', 'EASTPED', 'SOUTHPED', 'WESTPED']:
                                # 将各方向的行人相位添加到planScheme中
                                phaseForAllPedInPlanScheme = {phaseNameForAllPed: copy.deepcopy(phase[phaseName])}
                                planSchemeMajor.append(phaseForAllPedInPlanScheme)
                                # 在result2中也将全行人相位改为各方向的行人相位
                                phaseForAllPedInResult2 = {phaseNameForAllPed: copy.deepcopy(phaseInfoObj[phaseName])}
                                result2.append(phaseForAllPedInResult2)
                        else:
                            planSchemeMajor.append(phase)


                    # Update 该阶段最晚的相位结束时间
                    maxEndTimeOfStage = max(maxEndTimeOfStage, endTime)
                    # ---------------------------------------------------------------------------------------
                # 执行完一个阶段后，更新时刻游标（即下一个阶段的开始时刻）
                curStartTime = max(curStartTime, maxEndTimeOfStage)
                
        # The object is a ring style
        elif 'ringStyle' in obj.keys():
            ringList = obj["ringStyle"]
            if type(ringList[0]) != list:  # Type 2 format error
                ringList = [ringList]
            startTimeOfRing = curStartTime
            #print(ringList)
            for ring in ringList:
                curStartTime = startTimeOfRing
                for objInRing in ring:   # the element in a ring could be a phase or a stageStyle
                    if 'stageStyle' in objInRing.keys():  # The element is a stageStyle
                        stageList = objInRing["stageStyle"]
                        if type(stageList[0]) != list:  # Type 2 format error
                            stageList = [stageList] 
                        for stage in stageList:
                            maxEndTimeOfStage = -1  # 记录该阶段的最晚的结束时间
                            for phaseRaw in stage:
                                phaseNameRaw = helper_getSubValueFromPhase('phaseName', phaseRaw) # get raw phaseName                
                                #phase = {phaseNameFormatting(phaseNameRaw): phase[phaseNameRaw]} # update the phase obj
                                phaseNameFormatted = helper_getSubValueFromPhase('phaseName', phaseRaw) # get standard phaseName
                                phaseNameFormatted = phaseNameFormatting(phaseNameRaw)

                                # Calculate and assign attributes for each phase separated from phaseNameRaw---------------------------------------
                                phaseNameSeparatedList = helper_separateCombinedOppositeMovements(phaseNameFormatted)
                                for phaseName in phaseNameSeparatedList:
                                    phase = {phaseName: phaseRaw[phaseNameRaw]} 

                                    # 写入该相位的order 
                                    order = helper_AssignPhaseOrder(planSchemeMajor, phaseName)
                                    phase[phaseName].update({'phaseOrder': order}) # 该相位的order             

                                    # grab phaseInfo from result2
                                    phaseInfoObj = helper_getPhaseInfo(phaseName, order, result2)
                                    #if phaseInfoObj != None:
                                    phaseInfoObj = {phaseName: {}} if phaseInfoObj == None else phaseInfoObj
                                    phase[phaseName].update(phaseInfoObj[phaseName]) # merge the phase info from result1 and result2

                                    # infer the split's startTime, endTime, and split based on the counterparts of greenTime, if needed.
                                    helper_textualStartAndEndTime(phase, cycleLength)
                                    helper_inferStartAndEndTime(phase)
                                    helper_inferSplitAndGreen(phase)
                                    startTime = helper_getSubValueFromPhase('startTime', phase)
                                    split = helper_getSubValueFromPhase('split', phase)
                                    if split == 0 or type(split) != int: # 如果相位时长为0，大概是因为跟随相位被误写到了result1中，忽略这样的相位
                                        continue
                                    endTime = helper_getSubValueFromPhase('endTime', phase)

                                    # Assign start time if missing, as curStartTime
                                    if startTime == None:
                                        startTime = curStartTime
                                        phase[phaseName].update({"startTime": startTime})

                                    # 相位时间信息的容错处理
                                    # 要求startTime、endTime、split中，至少有两个不为None；否则，忽略该相位
                                    if (endTime != None) + (split != None) + (startTime != None) < 2:
                                        continue

                                    # Calculate split from start and end time of the phase if possible                            
                                    if split == None and startTime != None and endTime != None:
                                        split = helper_calcSplitFromStartAndEndTime(startTime, endTime) #helper_calcSplitFromGreenTime(phase)

                                    # Calculate end time if needed             
                                    if endTime == None and split != None: # Use startTime and split
                                        endTime = startTime + split
                                        endTime = helper_modifyCyclicTimepoint(endTime, cycleLength)
                                        phase[phaseName].update({"endTime": endTime})
                                    else: # endTime cannot be located. Will throw error?
                                        pass

                                    # 将完整的该相位的信息写入planSchemeMajor
                                    if '全行人' in phaseName:
                                        for phaseNameForAllPed in ['北行人', '东行人', '南行人', '西行人']:
                                            # 将各方向的行人相位添加到planScheme中
                                            phaseForAllPedInPlanScheme = {phaseNameForAllPed: copy.deepcopy(phase[phaseName])}
                                            planSchemeMajor.append(phaseForAllPedInPlanScheme)
                                            # 在result2中也将全行人相位改为各方向的行人相位
                                            phaseForAllPedInResult2 = {phaseNameForAllPed: copy.deepcopy(phaseInfoObj[phaseName])}
                                            result2.append(phaseForAllPedInResult2)
                                    elif 'ALLPED' in phaseName:
                                        for phaseNameForAllPed in ['NORTHPED', 'EASTPED', 'SOUTHPED', 'WESTPED']:
                                            # 将各方向的行人相位添加到planScheme中
                                            phaseForAllPedInPlanScheme = {phaseNameForAllPed: copy.deepcopy(phase[phaseName])}
                                            planSchemeMajor.append(phaseForAllPedInPlanScheme)
                                            # 在result2中也将全行人相位改为各方向的行人相位
                                            phaseForAllPedInResult2 = {phaseNameForAllPed: copy.deepcopy(phaseInfoObj[phaseName])}
                                            result2.append(phaseForAllPedInResult2)
                                    else:
                                        planSchemeMajor.append(phase)
                                # ---------------------------------------------------------------------------------------
                            # 执行完一个阶段后，更新时刻游标（即下一个阶段的开始时刻）
                            curStartTime = max(curStartTime, endTime)

                    else:                           # The element is a phase
                        phaseRaw = objInRing #.copy()
                        phaseNameRaw = helper_getSubValueFromPhase('phaseName', phaseRaw) # get raw phaseName                
                        #phase = {phaseNameFormatting(phaseNameRaw): phase[phaseNameRaw]} # update the phase obj
                        phaseNameFormatted = helper_getSubValueFromPhase('phaseName', phaseRaw) # get standard phaseName
                        phaseNameFormatted = phaseNameFormatting(phaseNameRaw)

                        # Calculate and assign attributes for each phase separated from phaseNameRaw---------------------------------------
                        phaseNameSeparatedList = helper_separateCombinedOppositeMovements(phaseNameFormatted)
                        for phaseName in phaseNameSeparatedList:
                            phase = {phaseName: phaseRaw[phaseNameRaw]} 

                            # 写入该相位的order 
                            order = helper_AssignPhaseOrder(planSchemeMajor, phaseName)
                            phase[phaseName].update({'phaseOrder': order}) # 该相位的order             

                            # grab phaseInfo from result2
                            phaseInfoObj = helper_getPhaseInfo(phaseName, order, result2)
                            #if phaseInfoObj != None:
                            phaseInfoObj = {phaseName: {}} if phaseInfoObj == None else phaseInfoObj
                            phase[phaseName].update(phaseInfoObj[phaseName]) # merge the phase info from result1 and result2

                            # infer the split's startTime, endTime, and split based on the counterparts of greenTime, if needed.
                            helper_textualStartAndEndTime(phase, cycleLength)
                            helper_inferStartAndEndTime(phase)
                            helper_inferSplitAndGreen(phase)
                            startTime = helper_getSubValueFromPhase('startTime', phase)
                            split = helper_getSubValueFromPhase('split', phase)
                            if split == 0 or type(split) != int: # 如果相位时长为0，大概是因为跟随相位被误写到了result1中，忽略这样的相位
                                continue
                            endTime = helper_getSubValueFromPhase('endTime', phase)

                            # Assign start time if missing, as curStartTime
                            if startTime == None:
                                startTime = curStartTime
                                phase[phaseName].update({"startTime": startTime})

                            # 相位时间信息的容错处理
                            # 要求startTime、endTime、split中，至少有两个不为None；否则，忽略该相位
                            if (endTime != None) + (split != None) + (startTime != None) < 2:
                                continue

                            # Calculate split from start and end time of the phase if possible                            
                            if split == None and startTime != None and endTime != None:
                                split = helper_calcSplitFromStartAndEndTime(startTime, endTime) #helper_calcSplitFromGreenTime(phase)

                            # Calculate end time if needed             
                            if endTime == None and split != None: # Use startTime and split
                                endTime = startTime + split
                                endTime = helper_modifyCyclicTimepoint(endTime, cycleLength)
                                phase[phaseName].update({"endTime": endTime})
                            else: # endTime cannot be located. Will throw error?
                                pass

                            # 将完整的该相位的信息写入planSchemeMajor
                            if '全行人' in phaseName:
                                for phaseNameForAllPed in ['北行人', '东行人', '南行人', '西行人']:
                                    # 将各方向的行人相位添加到planScheme中
                                    phaseForAllPedInPlanScheme = {phaseNameForAllPed: copy.deepcopy(phase[phaseName])}
                                    planSchemeMajor.append(phaseForAllPedInPlanScheme)
                                    # 在result2中也将全行人相位改为各方向的行人相位
                                    phaseForAllPedInResult2 = {phaseNameForAllPed: copy.deepcopy(phaseInfoObj[phaseName])}
                                    result2.append(phaseForAllPedInResult2)
                            elif 'ALLPED' in phaseName:
                                for phaseNameForAllPed in ['NORTHPED', 'EASTPED', 'SOUTHPED', 'WESTPED']:
                                    # 将各方向的行人相位添加到planScheme中
                                    phaseForAllPedInPlanScheme = {phaseNameForAllPed: copy.deepcopy(phase[phaseName])}
                                    planSchemeMajor.append(phaseForAllPedInPlanScheme)
                                    # 在result2中也将全行人相位改为各方向的行人相位
                                    phaseForAllPedInResult2 = {phaseNameForAllPed: copy.deepcopy(phaseInfoObj[phaseName])}
                                    result2.append(phaseForAllPedInResult2)
                            else:
                                planSchemeMajor.append(phase)
                        # ---------------------------------------------------------------------------------------
                        # 执行完一个阶段后，更新时刻游标（即下一个阶段的开始时刻）
                        curStartTime = max(curStartTime, endTime)


    # Step 2: Merge major phases

    # Update cycle length
    cycleLength = getCycleLengthOfPlanScheme(planSchemeMajor)
    # merge major phases
    planSchemeMajorMerged = mergeConnectedPhaseInPlanScheme(planSchemeMajor)
    #print(planSchemeMajorMerged)

    # Step 3: Add overlapped phases and standalone phases

    # Copy all the merged major phases into planSchemeMinorAdded
    planSchemeMinorAdded = []
    for phase in planSchemeMajorMerged:    
        planSchemeMinorAdded.append(phase.copy())
    # Get all phase names in planSchemeMajorMerged
    allPhaseNamesInPlanSchemeMajorMerged = set([ helper_getSubValueFromPhase('phaseName', _) for _ in planSchemeMajorMerged])

    result2 = helper_updateConcurrentPhaseAttribute(result2, planSchemeMajorMerged)
    #print(result2)

    # Calculate the split for each concurrent phase in the updated result2.
    # Deal with each phase in result2. If not already in planSchemeMajor, then add as a concurrent phase or standalone phase
    for phase in result2:
        phaseName = helper_getSubValueFromPhase('phaseName', phase)
        if phaseName in allPhaseNamesInPlanSchemeMajorMerged:
            continue
        # Phase info preparation: startTime, endTime and split
        flagStandalonePhase = False
        helper_textualStartAndEndTime(phase, cycleLength)
        helper_inferStartAndEndTime(phase)
        helper_inferSplitAndGreen(phase)
        startTime = helper_getSubValueFromPhase('startTime', phase)
        split = helper_getSubValueFromPhase('split', phase)
        endTime = helper_getSubValueFromPhase('endTime', phase)
        # 要求startTime、endTime、split中，至少有两个不为None；否则，忽略该相位
        if (endTime != None) + (split != None) + (startTime != None) >= 2:
            flagStandalonePhase = True

        # 处理跟随相位 concurrent phases（优先尝试作为独立相位，然后再尝试跟随相位，最后使用默认跟随相位）
        # Treat the phase as a standalone phase. Try to identify startTime and endTime.
        # 【Case 1】：Standalone phase
        if flagStandalonePhase:        
            # Calculate split from start and end time of the phase if possible                            
            if split == None and startTime != None and endTime != None:
                split = helper_calcSplitFromStartAndEndTime(startTime, endTime)

            # Calculate end time if needed             
            if endTime == None and split != None and startTime != None:   # Use startTime and split
                endTime = startTime + split
                endTime = helper_modifyCyclicTimepoint(endTime, cycleLength)

            # Update the time related value of the standalone phase, and append in planSchemeMinorAdded
            phaseCopy = copy.deepcopy(phase)
            phaseCopy[phaseName].update({"startTime": startTime, "split": split, "endTime": endTime})
            planSchemeMinorAdded.append(phaseCopy)

        else:
            parentPhaseName = helper_getSubValueFromPhase('parentPhase', phase)
            parentPhaseOrder = helper_getSubValueFromPhase('overlapNum', phase)
            # 【Case 2】： Overlapped phase
            if parentPhaseName == None:# and majorPhaseNameAndOrder != 'default':
                continue
            flagMajorPhaseFound = False

            parentPhase = helper_getPhaseInfo(parentPhaseName, parentPhaseOrder, planSchemeMajorMerged)
            parentPhase = helper_getPhaseInfo(parentPhaseName, parentPhaseOrder, result2) if parentPhase == None else parentPhase

            # Copy the time related value of the major phase
            startTime = helper_getSubValueFromPhase('startTime', parentPhase)
            split = helper_getSubValueFromPhase('split', parentPhase)
            endTime = helper_getSubValueFromPhase('endTime', parentPhase)
            redAmber = helper_getSubValueFromPhase('redAmber', parentPhase)
            allRed = helper_getSubValueFromPhase('allRed', parentPhase)
            yellow = helper_getSubValueFromPhase('yellow', parentPhase)
            greenFlash = helper_getSubValueFromPhase('greenFlash', parentPhase)
            # Update the time related value of the concurrent phase, and append in planSchemeMinorAdded
            phaseCopy = copy.deepcopy(phase)
            # Copy startTime, split, endTime of the major phase
            phaseCopy[phaseName].update({"startTime": startTime, "split": split, "endTime": endTime})
            # Copy redAmber and allRed of the major phase (if any)
            if '行人' in phaseName or 'PED' in phaseName:
                # Logic for redAmber and lateStart for concurrent overlapping ped phase
                lateStartOfOverlapPedPhase = helper_getSubValueFromPhase('lateStart', phase) + redAmber
                # Update attributes for overlapping ped phase
                phaseCopy[phaseName].update({"allRed": allRed, "lateStart": lateStartOfOverlapPedPhase, "yellow": yellow})
            else:
                phaseCopy[phaseName].update({"allRed": allRed, "redAmber": redAmber, "yellow": yellow, "greenFlash":greenFlash})
            planSchemeMinorAdded.append(phaseCopy)


    # Step 4: Merge overlapped phases and standalone phases

    # Update cycleLength again, after overlapped phases and standalone phases are added.
    cycleLength = getCycleLengthOfPlanScheme(planSchemeMinorAdded)
    # Merge minor phases
    planSchemeMinorMerged = mergeConnectedPhaseInPlanScheme(planSchemeMinorAdded)

    # Final updating on each phase info
    for phase in planSchemeMinorMerged:
        helper_inferStartAndEndTime(phase)
        helper_inferSplitAndGreen(phase)

    # 记录Chat方案的相位结果
    resOfChat2SPaT.update({"planSchemeMinorMerged": planSchemeMinorMerged})

    # Remove dummyPhases in the final plan result
    planSchemeMinorMerged = [_ for _ in planSchemeMinorMerged if helper_getSubValueFromPhase('phaseName', _) != 'DUMMYPHASE']

    # Step 5: Plan validation and visualization

    # Step 5.1：cycle length validation
    #print(cycleLength, cycleLengthByUser)
    if cycleLengthByUser == None or cycleLength == cycleLengthByUser:  # 周期时长未指定，或指定的周期与计算值相同
        resOfChat2SPaT.update({'warningMsgCycleLength': {}})  
    else:
        # 组装方案后周期时长与对话指定的不一致，写入warning信息。
        resOfChat2SPaT.update({'warningMsgCycleLength': {'实际的周期时长': cycleLength, '对话中指定的周期时长': cycleLengthByUser,\
                                                        'actual cycle length': cycleLength, 'cycle length from chat': cycleLengthByUser}})

    # Step 5.2：signal head validation
    # TODO
    # This part is skipped for the study, but should be extended for real-world applications.

    # Step 5.3：generate second-by-second traffic light color code
    allPhaseNamesInPlanSchemeMinorMerged = set([ helper_getSubValueFromPhase('phaseName', _) for _ in planSchemeMinorMerged])
    dict_lightColorRec = {_: [0] * cycleLength for _ in allPhaseNamesInPlanSchemeMinorMerged}
    for phase in planSchemeMinorMerged:
        # Extract phase info
        phaseName = helper_getSubValueFromPhase('phaseName', phase)
        isPermissive = helper_getSubValueFromPhase('isPermissive', phase)
        startTime = helper_getSubValueFromPhase('startTime', phase)
        endTime = helper_getSubValueFromPhase('endTime', phase)
        startOfGreen = helper_getSubValueFromPhase('startTime', phase)
        endOfGreen = helper_getSubValueFromPhase('endTime', phase)
        split = helper_getSubValueFromPhase('split', phase)
        lateStart = helper_getSubValueFromPhase('lateStart', phase)
        greenFlash = helper_getSubValueFromPhase('greenFlash', phase)
        yellow = helper_getSubValueFromPhase('yellow', phase)
        allRed = helper_getSubValueFromPhase('allRed', phase)
        redAmber = helper_getSubValueFromPhase('redAmber', phase)
        earlyCutOff = helper_getSubValueFromPhase('earlyCutOff', phase)
        countDown = helper_getSubValueFromPhase('countDown', phase)

        lightColorRec = dict_lightColorRec[phaseName]

        # 对行人和机动车相位分别画图
        if '行人' in phaseName or 'PED' in phaseName:  # ped phase
            walk = split - lateStart - countDown - allRed - earlyCutOff # 由split计算出的walk时长
            lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart, walk, cycleLength, colorCode=2)
            lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart+walk, countDown, cycleLength, colorCode=3)
            dict_lightColorRec.update({phaseName: lightColorRec})
        else:  # vehicular phases
            greenTimeWithoutGreenFlash = split - lateStart - greenFlash - yellow - allRed - earlyCutOff  # get green duration from split
            # Draw green and greenFlash / permissive green
            if isPermissive == 0:
                # green (in green)
                lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart, greenTimeWithoutGreenFlash, cycleLength, colorCode=2)
                lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart+greenTimeWithoutGreenFlash, greenFlash, cycleLength, colorCode=3)
            else:
                # permissive green (in grey)
                lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart, greenTimeWithoutGreenFlash+greenFlash, cycleLength, colorCode=-1)
            # yellow (in yellow)
            lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart+greenTimeWithoutGreenFlash+greenFlash, yellow, cycleLength, colorCode=1)
            # redAmber (in yellow+red)
            lightColorRec = helper_paintLightColor(lightColorRec, startTime+lateStart, redAmber, cycleLength, colorCode=4)
            dict_lightColorRec.update({phaseName: lightColorRec})

    resOfChat2SPaT.update({'dict_lightColorRec': dict_lightColorRec})        

    # Step 5.4: validation on conflicted movements
    conflictMatrix = {'北直行': ['东直行', '西直行', '东左转', '西左转', '北行人', '北行人二次过街A', '南行人', '南行人二次过街B', '南左转'],
                      '东直行': ['南直行', '北直行', '南左转', '北左转', '东行人', '东行人二次过街A', '西行人', '西行人二次过街B', '西左转'],
                      '南直行': ['西直行', '东直行', '西左转', '东左转', '南行人', '南行人二次过街A', '北行人', '北行人二次过街B', '北左转'],
                      '西直行': ['北直行', '南直行', '北左转', '南左转', '西行人', '西行人二次过街A', '东行人', '东行人二次过街B', '东左转'],

                      '北左转': ['东直行', '西直行', '东左转', '西左转', '北行人', '北行人二次过街A', '南直行'],
                      '东左转': ['南直行', '北直行', '南左转', '北左转', '东行人', '东行人二次过街A', '西直行'],
                      '南左转': ['西直行', '东直行', '西左转', '东左转', '南行人', '南行人二次过街A', '北直行'],
                      '西左转': ['北直行', '南直行', '北左转', '南左转', '西行人', '西行人二次过街A', '东直行'],

                      'SBT': ['WBT', 'EBT', 'WBL', 'EBL', 'NORTHPED', 'NORTHPEDa', 'SOUTHPED', 'SOUTHPEDB', 'NBL'],
                      'WBT': ['NBT', 'SBT', 'NBL', 'SBL', 'EASTPED', 'EASTPEDA', 'WESTPED', 'WESTPEDB', 'EBL'],
                      'NBT': ['EBT', 'WBT', 'EBL', 'WBL', 'SOUTHPED', 'SOUTHPEDA', 'NORTHPED', 'NORTHPEDB', 'SBL'],
                      'EBT': ['SBT', 'NBT', 'SBL', 'NBL', 'WESTPED', 'WESTPEDA', 'EASTPED', 'EASTPEDB', 'WBL'],

                      'SBL': ['WBT', 'EBT', 'WBL', 'EBL', 'NORTHPED', 'NORTHPEDA', 'NBT'],
                      'WBL': ['NBT', 'SBT', 'NBL', 'SBL', 'EASTPED', 'EASTPEDA', 'EBT'],
                      'NBL': ['EBT', 'WBT', 'EBL', 'WBL', 'SOUTHPED', 'SOUTHPEDA', 'SBT'],
                      'EBL': ['SBT', 'NBT', 'SBL', 'NBL', 'WESTPED', 'WESTPEDA', 'WBT']
                     }
    warningMsgConflictPhases = {}
    checkedPhaseNames = []  # 记录已经对比过的相位
    for phaseName in dict_lightColorRec:
        if phaseName not in conflictMatrix: # 该相位无冲突相位，跳过
            continue
        for phaseConflictName in conflictMatrix[phaseName]:
            if phaseConflictName in checkedPhaseNames: # 该相位已校验过，跳过
                continue
            if phaseConflictName not in dict_lightColorRec:  # 该相位不在Chat方案中，无需校验
                continue
            conflictTimeIntervals = helper_areConflictingPhasesTimedSimultaneously(phaseName, phaseConflictName,\
                                                                   dict_lightColorRec[phaseName], dict_lightColorRec[phaseConflictName])
            # print(phaseName, phaseConflictName, conflictTimeIntervals)
            if len(conflictTimeIntervals) > 0:
                warningMsgConflictPhases.update({'%s|%s'%(phaseName, phaseConflictName): conflictTimeIntervals})

        checkedPhaseNames.append(phaseName)

    resOfChat2SPaT.update({'warningMsgConflictPhases': warningMsgConflictPhases})  # 记录冲突相位的校验结果

    # Step 5.5：Ped WALK interval validation
    warningMsgPedWalk = checkPedWalkIntvl(dict_lightColorRec)
    resOfChat2SPaT.update({'warningMsgPedWalk': warningMsgPedWalk})

    # Step 5.6：Assign validation result for the generatd plan
    if len(resOfChat2SPaT['warningMsgConflictPhases']) == 0 and len(resOfChat2SPaT['warningMsgPedWalk']) == 0:
        resOfChat2SPaT.update({'isValid': 1}) 
        print('【The generated plan is VALID.】')
    else:
        resOfChat2SPaT.update({'isValid': 0}) 
        print('【The generated plan is INVALID!】', resOfChat2SPaT['warningMsgConflictPhases'], resOfChat2SPaT['warningMsgPedWalk'])

    # Plan visualization
    if plot == True: 
        figW, figH = 12, 8
        fig, ax = plt.subplots(figsize=(figW, figH))
        ax.plot([],[],color="cyan")

        unitHeight = 1  # 单位相位的高度
        spaceBtwBars = 0.1
        cnt = 0         # 已画的相位的个数（先算出总个数，然后从上往下画）
        dict_y1OfPhases = {}  # 记录各相位的bar的y坐标；同名相位的

        planSchemeSorted = sorted(planSchemeMinorMerged, key=lambda x: helper_getSubValueFromPhase('startTime', x), reverse=False)
        phasePlotNum = len(set([helper_getSubValueFromPhase('phaseName', _) for _ in planSchemeSorted]))  # non-dpulicated phase names


        for phase in planSchemeSorted:
            # Extract phase info
            phaseName = helper_getSubValueFromPhase('phaseName', phase)
            isPermissive = helper_getSubValueFromPhase('isPermissive', phase)
            startTime = helper_getSubValueFromPhase('startTime', phase)
            endTime = helper_getSubValueFromPhase('endTime', phase)
            split = helper_getSubValueFromPhase('split', phase)
            lateStart = helper_getSubValueFromPhase('lateStart', phase)
            greenFlash = helper_getSubValueFromPhase('greenFlash', phase)
            yellow = helper_getSubValueFromPhase('yellow', phase)
            allRed = helper_getSubValueFromPhase('allRed', phase)
            redAmber = helper_getSubValueFromPhase('redAmber', phase)
            earlyCutOff = helper_getSubValueFromPhase('earlyCutOff', phase)
            countDown = helper_getSubValueFromPhase('countDown', phase)

            # Draw rectangles
            # y1 of Anchor point
            if phaseName not in dict_y1OfPhases:
                y1 = unitHeight*(phasePlotNum-cnt)
                dict_y1OfPhases.update({phaseName: y1})
                # Update cnt
                cnt += 1
                # paint the whole cycle as red first
                drawRectangleInCycle(ax, 0, cycleLength, y1, unitHeight-spaceBtwBars, cycleLength, 'red')
            else:
                y1 = dict_y1OfPhases[phaseName]  # use the y-coord of the phase which already exists, to draw on the same row
            # 对行人和机动车相位分别画图
            if '行人' in phaseName or 'PED' in phaseName:  # ped phase
                walk = split - lateStart - countDown - allRed - earlyCutOff # 由split计算出的walk时长
                # lateStart (in red)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime, cycleLength), lateStart,\
                                     y1, unitHeight-spaceBtwBars, cycleLength, 'red')
                # walk (in green)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart, cycleLength), walk,\
                                     y1, unitHeight-spaceBtwBars, cycleLength, 'green')
                # flashing don't walk (in green dashed)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart + walk, cycleLength), countDown,\
                                     y1, unitHeight-spaceBtwBars, cycleLength, 'lightgreen')
            else:  # vehicular phases
                greenTimeWithoutGreenFlash = split - lateStart - greenFlash - yellow - allRed - earlyCutOff  # 由split计算出的‘真’绿灯时长
                # lateStart (in red)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime, cycleLength), lateStart,\
                                     y1, unitHeight-spaceBtwBars, cycleLength, 'red')
                # Draw green and greenFlash / permissive green
                if isPermissive == 0:
                    # green (in green)
                    drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart, cycleLength), greenTimeWithoutGreenFlash,\
                                         y1, unitHeight-spaceBtwBars, cycleLength, 'green')
                    # greenFlash (in green dashed)
                    drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart + greenTimeWithoutGreenFlash, cycleLength), greenFlash,\
                                         y1, unitHeight-spaceBtwBars, cycleLength, 'lightgreen')
                else:
                    # permissive green (in grey)
                    permissiveDuration = split - lateStart - yellow - allRed - earlyCutOff  # duration of lights off for permissive phase
                    drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart, cycleLength), permissiveDuration,\
                                         y1, unitHeight-spaceBtwBars, cycleLength, 'dimgrey')
                # yellow (in yellow)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart + greenTimeWithoutGreenFlash + greenFlash, cycleLength), yellow,\
                                     y1, unitHeight-spaceBtwBars, cycleLength, 'yellow')
                # allRed (in red)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart + greenTimeWithoutGreenFlash + greenFlash + yellow, cycleLength), allRed,\
                                     y1, unitHeight-spaceBtwBars, cycleLength, 'red')
                # redAmber (in yellow+red)
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart, cycleLength), redAmber,\
                                     y1, 0.5*(unitHeight-spaceBtwBars), cycleLength, 'yellow')
                drawRectangleInCycle(ax, helper_modifyCyclicTimepoint(startTime + lateStart, cycleLength), redAmber,\
                                     y1+0.5*(unitHeight-spaceBtwBars), 0.5*(unitHeight-spaceBtwBars), cycleLength, 'red')

            # Add text and symbol of the phase
            fontsizeModifier = calcFontsizeModifier(figH, phasePlotNum)
            plt.rcParams['font.family']=['SimHei'] #用来正常显示中文标签
            ax.text(helper_modifyCyclicTimepoint(startTime + lateStart + redAmber + 1, cycleLength), y1 + 0.51, phaseName, style='italic', fontsize=int(14*fontsizeModifier), rotation = 0)  # 写入相位名称
            text, rotation = getPhasePlotLabelAndRotation(phaseName)
            plt.rcParams['font.family'] = 'DejaVu Sans'  # Ensure the font supports Unicode
            ax.text(helper_modifyCyclicTimepoint(startTime + lateStart + redAmber + 1, cycleLength), y1 + 0.18, text, fontsize=int(15*fontsizeModifier), rotation = rotation)

        # Set labels, titles, ticks
        ax.set_ylabel('Phases',  fontsize=16, color='k')
        ax.set_xlabel('Timeline within a cycle',  fontsize=16, color='k')
        ax.yaxis.set_ticks([]) 
        xtick_list = [_ * 10 for _ in range(cycleLength//10 + 1)]
        if cycleLength % 10 > 0:
            if cycleLength % 10 < 3:  # If the last tick is too close to cycleLength, remove it
                xtick_list  =xtick_list[:-1]
            xtick_list.append(cycleLength)
        plt.xticks(xtick_list, xtick_list, fontsize=12, rotation=0)

        plt.show()

    return resOfChat2SPaT

# HELPER FUNCTIONS
# 【Step 1-4】helper functions 
# For plan scheme generation

# separate phase name that is recorded as a combination of two phases (same movement of opposite directions).
def helper_separateCombinedOppositeMovements(phaseName):
    '''Fault tolerance function. Mostly used for Chinese phase names, as they are more likely to be recorded as a combined name by small LLMs.
    E.g., phase name '南北直行' is split into two phase names, '南直行' and '北直行'.'''
    phaseName = phaseName.upper()
    dictOpposite = {'东': '西', '西': '东', '北': '南', '南': '北'}
    res = []
    if len(phaseName) <= 3:
        return [phaseName]
    if phaseName[1] in dictOpposite and phaseName[0] == dictOpposite[phaseName[1]]:
        return [phaseName[0]+phaseName[2:], phaseName[1]+phaseName[2:]]
    else:
        return [phaseName]
# helper: convert textual phase's start and end time to number
def helper_textualStartAndEndTime(phase, cycleLength=None):
    phaseName = helper_getSubValueFromPhase('phaseName', phase)
    # endTime
    endTime = helper_getSubValueFromPhase('endTime', phase)
    if endTime == 'cycleLength':
        phase[phaseName].update({"endTime": cycleLength})
    # endOfGreen
    endOfGreen = helper_getSubValueFromPhase('endOfGreen', phase)
    if endOfGreen == 'cycleLength':
        phase[phaseName].update({"endOfGreen": cycleLength})
    
# helper: calculate split's (startTime,endTime) or green's (startOfGreen,endOfGreen) based on each other, if one exists and the other None.
def helper_inferStartAndEndTime(phase): #
    '''Infer start&end time of split and green, based on which is provided.
    phase - phase obj'''
    phaseName = helper_getSubValueFromPhase('phaseName', phase)
    # startTime: start time of the split
    startTime = helper_getSubValueFromPhase('startTime', phase)
    if startTime == None:
        startOfGreen = helper_getSubValueFromPhase('startOfGreen', phase)
        if startOfGreen != None:
            redAmber = helper_getSubValueFromPhase('redAmber', phase)
            lateStart = helper_getSubValueFromPhase('lateStart', phase)
            startTime = startOfGreen - lateStart - redAmber
            phase[phaseName].update({"startTime": startTime}) 
    
    # startOfGreen: start time of the green
    startOfGreen = helper_getSubValueFromPhase('startOfGreen', phase)
    if startOfGreen == None:
        startTime = helper_getSubValueFromPhase('startTime', phase)
        if startTime != None:
            redAmber = helper_getSubValueFromPhase('redAmber', phase)
            lateStart = helper_getSubValueFromPhase('lateStart', phase)  
            startOfGreen = startTime + lateStart + redAmber
            phase[phaseName].update({"startOfGreen": startOfGreen}) 
    
    # endTime: end time of the split
    endTime = helper_getSubValueFromPhase('endTime', phase)
    if endTime == None:
        endOfGreen = helper_getSubValueFromPhase('endOfGreen', phase)
        if endOfGreen != None:
            yellow = helper_getSubValueFromPhase('yellow', phase)
            allRed = helper_getSubValueFromPhase('allRed', phase)
            earlyCutOff = helper_getSubValueFromPhase('earlyCutOff', phase)
            endTime = endOfGreen + yellow + allRed + earlyCutOff
            phase[phaseName].update({"endTime": endTime})
    
    # endOfGreen: end time of the green
    endOfGreen = helper_getSubValueFromPhase('endOfGreen', phase)
    if endOfGreen == None:
        endTime = helper_getSubValueFromPhase('endTime', phase)
        if endTime != None:
            yellow = helper_getSubValueFromPhase('yellow', phase)
            allRed = helper_getSubValueFromPhase('allRed', phase)
            earlyCutOff = helper_getSubValueFromPhase('earlyCutOff', phase)
            endOfGreen = endTime - yellow - allRed - earlyCutOff
            phase[phaseName].update({"endOfGreen": endOfGreen})
    
    # TODO 周期未知的情况下，整出负数了怎么办？        
    return

# helper: calculate split based on greenTime, or vice versa.
def helper_inferSplitAndGreen(phase):  # 
    '''Infer split and greenTime from each other, depending on which one is provided.
    phase - phase obj'''
    phaseName = helper_getSubValueFromPhase('phaseName', phase)
    # split: duration of the split
    split = helper_getSubValueFromPhase('split', phase)
    if split == None:
        greenTime = helper_getSubValueFromPhase('greenTime', phase)
        if greenTime != None and type(greenTime) == int:
            earlyCutOff = helper_getSubValueFromPhase('earlyCutOff', phase)
            lateStart = helper_getSubValueFromPhase('lateStart', phase)
            yellow = helper_getSubValueFromPhase('yellow', phase)
            allRed = helper_getSubValueFromPhase('allRed', phase)
            redAmber = helper_getSubValueFromPhase('redAmber', phase)
            split = lateStart + redAmber + greenTime + earlyCutOff + yellow + allRed
            phase[phaseName].update({"split": split}) 
    
    # greenTime: duration of the green time
    greenTime = helper_getSubValueFromPhase('greenTime', phase)
    if greenTime == None:
        split = helper_getSubValueFromPhase('split', phase)
        if split != None and type(split) == int:
            earlyCutOff = helper_getSubValueFromPhase('earlyCutOff', phase)
            lateStart = helper_getSubValueFromPhase('lateStart', phase)
            yellow = helper_getSubValueFromPhase('yellow', phase)
            allRed = helper_getSubValueFromPhase('allRed', phase)
            redAmber = helper_getSubValueFromPhase('redAmber', phase)
            greenTime = split - lateStart - redAmber - earlyCutOff - yellow - allRed
            phase[phaseName].update({"greenTime": greenTime}) 

    return

# helper: map a timepoint to cycle
def helper_modifyCyclicTimepoint(t, cycleLength): # 
    '''cycleLength = 110, t=145 -> 35'''
    if t == cycleLength or cycleLength==None:
        return t
    return t%cycleLength

#0606 ABCD debug
def helper_updateConcurrentPhaseAttribute(result2, planSchemeMajorMerged):
    '''In step three, update phase attribute - result2.
    replace placeholder of parentPhase and overlapNum'''
    result2_formatted = []
    # Get all phase names in planSchemeMajorMerged
    allPhaseNamesInPlanSchemeMajorMerged = set([ helper_getSubValueFromPhase('phaseName', _) for _ in planSchemeMajorMerged])
    # Work on the placeholders of each phase, and append it in the formatted result2 
    for phase in result2:
        phaseName = helper_getSubValueFromPhase('phaseName', phase)
        if phaseName in allPhaseNamesInPlanSchemeMajorMerged:  # The corresponding phase is already in the scheme result
            result2_formatted.append(phase)
            continue
        if '全行人' in phaseName or 'ALLPED' in phaseName:  # All ped phase
            # result2_formatted.append(phase)
            continue
        # Replace placeholder for parentPhaseName
        parentPhaseName = helper_getSubValueFromPhase('parentPhase', phase)  # Search for the parent phase to follow
        # if the phase does not have a parent phase, it is not a overlapped phase, skip.
        if parentPhaseName == None:
            result2_formatted.append(phase)
            continue
        elif parentPhaseName == 'default':
            parentPhaseName = helper_getDefaultParentPhaseList(phaseName)
            phase[phaseName].update({'parentPhase': parentPhaseName})
        elif ',' in parentPhaseName:  # multiple parent phases are recorded as one, e.g. parentPhase = 'NBT, SBT'
            parentPhaseName = [_.replace(' ', '').replace('[', '').replace(']', '') for _ in parentPhaseName.split(',')]
        # Update placeholder for overlapNum
        parentPhaseOrder = helper_getSubValueFromPhase('overlapNum', phase)  # Search for the major phase to follow

        # The phase is a concurrent phase, replace placeholder for parentPhaseOrder, if any
        # Format parentPhaseName as list
        if type(parentPhaseName) != list:  
            parentPhaseNameList = [parentPhaseName]
        else:
            parentPhaseNameList = parentPhaseName
        if parentPhaseOrder == None or parentPhaseOrder == 0:
            for parentPhaseName in parentPhaseNameList:
                parentPhaseName = phaseNameFormatting(parentPhaseName)
                for m in range(1, 4):  # 默认最多主相位有三个阶段，分别跟随一下
                    parentPhase = helper_getPhaseInfo(parentPhaseName, m, planSchemeMajorMerged)
                    parentPhase = helper_getPhaseInfo(parentPhaseName, m, result2) if parentPhase == None else parentPhase
                    if parentPhase != None:
                        phaseCopy = copy.deepcopy(phase)
                        phaseCopy[phaseName].update({'parentPhase': parentPhaseName, 'overlapNum': m})
                        result2_formatted.append(phaseCopy)

        # follow the sepcified occurrence of the parent phase
        else:
            for parentPhaseName in parentPhaseNameList:
                parentPhaseName = phaseNameFormatting(parentPhaseName)
                flagMajorPhaseFound = False
                m = parentPhaseOrder
                while m > 0:
                    parentPhase = helper_getPhaseInfo(parentPhaseName, m, planSchemeMajorMerged)  
                    parentPhase = helper_getPhaseInfo(parentPhaseName, m, result2) if parentPhase == None else parentPhase
                    if parentPhase != None:  # The major phase stage to follow is found
                        flagMajorPhaseFound = True
                        break
                    m -= 1
                if flagMajorPhaseFound == True:
                    phaseCopy = copy.deepcopy(phase)
                    phaseCopy[phaseName].update({'parentPhase': parentPhaseName, 'overlapNum': m})
                    result2_formatted.append(phaseCopy)

    return result2_formatted

# helper: 判断两个相位-阶段是否相连通
def helper_twoPhaseStagesConnected(phase1, phase2, cycleLength): # 
    '''The two phase stages are treated as connected if their phase name and permissive are the same,
    and their truncated start and end time (by early cut off and late start) are overlapped.
    Return 1 if connected, 0 otherwise'''
    # Get info of phase1
    phaseName1 = helper_getSubValueFromPhase('phaseName', phase1)
    isPermissive1 = helper_getSubValueFromPhase('isPermissive', phase1)
    startTime1 = helper_getSubValueFromPhase('startTime', phase1)
    endTime1 = helper_getSubValueFromPhase('endTime', phase1)
    startTimeTruncated1 = startTime1 + helper_getSubValueFromPhase('lateStart', phase1)
    endTimeTruncated1 = endTime1 - helper_getSubValueFromPhase('earlyCutOff', phase1)
    # Get info of phase2
    phaseName2 = helper_getSubValueFromPhase('phaseName', phase2)
    isPermissive2 = helper_getSubValueFromPhase('isPermissive', phase2)
    startTime2 = helper_getSubValueFromPhase('startTime', phase2)
    endTime2 = helper_getSubValueFromPhase('endTime', phase2)
    startTimeTruncated2 = startTime2 + helper_getSubValueFromPhase('lateStart', phase2)
    endTimeTruncated2 = endTime2 - helper_getSubValueFromPhase('earlyCutOff', phase2)
    # Compare
    if phaseName1 == phaseName2 and isPermissive1 == isPermissive2:  # Same name and same isPermissive
        if helper_timeIntersectsStartAndEndTime(startTimeTruncated1, startTimeTruncated2, endTimeTruncated2, cycleLength) >= 0 or\
           helper_timeIntersectsStartAndEndTime(endTimeTruncated1, startTimeTruncated2, endTimeTruncated2, cycleLength) >= 0:
            return 1
    return 0

# helper 判断给定时刻与给定的开始、结束时间是否相交的关系（共4种：-2-存在None值，0-等于开始时间、2-等于结束时间、1-相交、-1-不相交）
def helper_timeIntersectsStartAndEndTime(t, startTime, endTime, cycleLength):#
    '''The values of startTime and endTime are within [0, cycleLength)'''
    t = t % cycleLength
    startTime = startTime % cycleLength
    endTime = endTime % cycleLength
    if startTime == None or endTime == None:
        return -2
    if t == startTime:
        return 0
    elif t == endTime:
        return 2
    elif startTime < endTime and (t - startTime) * (t - endTime) < 0: # 开始时间小于结束时间
        return 1
    elif startTime > endTime and (t - startTime) * (t - endTime) > 0: # 开始时间大于结束时间
        return 1
    else:
        return -1

#
def mergeConnectedPhaseInPlanScheme(planScheme, cycleLength=None):
    '''在planScheme中寻找连通的相位阶段，并合并起来。输出处理后的planSchemeMerged'''
    planSchemeMerged = []  # Initialize result
    # cycle length
    if cycleLength == None:
        cycleLength = getCycleLengthOfPlanScheme(planScheme)  # Calculate cycle length directly from the given planScheme 
    #print(cycleLength)
    # DFS functions
    def dfs(node, visited, graph, component):
        visited[node] = True
        component.append(node)
        for neighbor in graph[node]:
            if not visited[neighbor]:
                dfs(neighbor, visited, graph, component)

    def build_graph(data):
        graph = {}
        for i, obj in enumerate(data):        
            graph[i] = []
            for j, other_obj in enumerate(data):
                if i != j:
                    # This helper function defines connection of phase stages
                    if helper_twoPhaseStagesConnected(obj, other_obj, cycleLength) == 1:
                        graph[i].append(j)
        return graph

    def find_connected_components(data):
        graph = build_graph(data)
        visited = [False] * len(data)
        components = []

        for i in range(len(data)):
            if not visited[i]:
                component = []
                dfs(i, visited, graph, component)
                components.append([data[j] for j in component])

        return components

    # 找到连通的组件
    components = find_connected_components(planScheme)

    # 合并相连通的相位，planSchemeMerged
    for connectedPhaseStageList in components:
        # print('合并前的同阶段相位list：', connectedPhaseStageList)
        mergedPhase = helper_mergeConnectedphaseStages(connectedPhaseStageList, cycleLength)
        phaseName = helper_getSubValueFromPhase('phaseName', mergedPhase)
        orderOfMergedPhase = helper_AssignPhaseOrder(planSchemeMerged, phaseName)
        mergedPhase[phaseName].update({'phaseOrder': orderOfMergedPhase})
        # print('合并后的相位', mergedPhase)

        # 将合并后的phase写入结果planSchemeMerged
        planSchemeMerged.append(mergedPhase)
    
    # return result
    return planSchemeMerged

# helper: merge connected phase stages
def helper_mergeConnectedphaseStages(connectedPhaseStageList, cycleLength):#
    '''connectedPhaseStageList is a list of connected phase stages, identified by DFS'''
    # If only one stage in the input, no need to merge.
    if len(connectedPhaseStageList) == 1:
        mergedPhase = connectedPhaseStageList[0].copy()
    
    # 获取相位名称
    phaseName = helper_getSubValueFromPhase('phaseName', connectedPhaseStageList[0])
    # 取所有阶段的所有key，逐个收集组成value的list。
    allKeys = set([])
    for phase in connectedPhaseStageList:
        for k in phase[phaseName].keys():
            allKeys.add(k)
    allKeys = list(allKeys)
    
    # 生成合并后的相位结构体；逐个key处理，按规则计算或根据默认值和用户输入处理
    phaseMerged = {phaseName: {}}    
    # 首先处理基于计算的key：split，startTime，endTime.
#     keysToCalculate = ['split', 'startTime', 'endTime', 'phaseOrder']
    startAndEndTimeList = [[helper_getSubValueFromPhase('startTime', phase),\
                            helper_getSubValueFromPhase('endTime', phase)] for phase in connectedPhaseStageList]
    startTime, endTime = helper_mergeStartAndEndTimeList(startAndEndTimeList, cycleLength)
    split = helper_calcSplitFromStartAndEndTime(startTime, endTime, cycleLength)
    phaseMerged[phaseName].update({"startTime": startTime, "endTime": endTime, "split": split})
    
    # 然后处理基于默认值和用户输入的key：lateStart, earlyCutOff，yellow，greenFlash等取第一个不等于默认值的值
    keysToCompareWithDefaultValue = ['phaseId', 'greenFlash', 'yellow', 'redAmber', 'allRed', 'lateStart', 'earlyCutOff',
                                    'isPermissive', 'countDown']
    for k in allKeys:
        if k not in keysToCompareWithDefaultValue:
            continue
        # 获取全部value,并使用用户赋予的非默认值
        nonDefaultValueListOfKey = []
        for phase in connectedPhaseStageList:
            if helper_getSubValueFromPhase(k, phase) != helper_getSubValueFromPhase(k, phase, getDefaultValue=True):
                nonDefaultValueListOfKey.append(helper_getSubValueFromPhase(k, phase))
        if len(nonDefaultValueListOfKey) > 0:    # 如果有非默认值，则保留该值赋给该key（只取第一个）
            valueSelected = nonDefaultValueListOfKey[0]
        else:
            valueSelected =  helper_getSubValueFromPhase(k, phase, getDefaultValue=True)
        phaseMerged[phaseName].update({k: valueSelected})
    
    return phaseMerged

# helper: merge the start and end time of multiple connected phase stages 
def helper_mergeStartAndEndTimeList(startAndEndTimeList, cycleLength):
    ''' Find the start and end times of the merged phase, based on the start and end time lists of all phase occurrences.
    The duration of each start and end time in the list are guaranteed to be connected (by DFS in the previous step).
    startAndEndTimeList[[10, 30], [25, 60], [90, 10]], cycleLength=100  -> [90, 60] '''
    # Check if any duration extends beyond the cycleLength (startTime > EndTime)
    startAndEndTimeList_New = []
    for startAndEndTime in startAndEndTimeList:
        startTime, endTime = startAndEndTime
        if startTime > endTime:
            startAndEndTime_Partitioned1 = [startTime, cycleLength]
            startAndEndTime_Partitioned2 = [0, endTime]
            startAndEndTimeList_New.append(startAndEndTime_Partitioned1)
            startAndEndTimeList_New.append(startAndEndTime_Partitioned2)
        else:
            startAndEndTimeList_New.append(startAndEndTime)
    
    # Find the start and end times of the merged phase
    tInSplitRec = [0] * cycleLength
    for t in range(cycleLength):
        flag_tInSplit = False
        for startAndEndTime in startAndEndTimeList_New:
            if t >= startAndEndTime[0] and  t < startAndEndTime[1]:
                flag_tInSplit = True
                break
        if flag_tInSplit == True:
            tInSplitRec[t] = 1  
    
    # get split's start and end time based on tInSplitRec
    startTimeMerged, endTimeMerged = -1, -1  # default value
    # start time
    for t in range(1, cycleLength):
        if tInSplitRec[t-1] == 0 and tInSplitRec[t] == 1:
            startTimeMerged = t
    # special case: start time = 0
    if startTimeMerged == -1:
        if tInSplitRec[0] == 1 and tInSplitRec[-1] == 0:
            startTimeMerged = 0
    # end time
    for t in range(0, cycleLength-1):
        if tInSplitRec[t] == 1 and tInSplitRec[t+1] == 0:
            endTimeMerged = t+1
    # special case: end time = last second
    if endTimeMerged == -1:
        if tInSplitRec[-1] == 1 and tInSplitRec[0] == 0:
            endTimeMerged = cycleLength
    
    return [startTimeMerged, endTimeMerged]

# helper: merge the start and end time of multiple connected phase stages
def helper_calcSplitFromStartAndEndTime(startTime, endTime, cycleLength=None):#
    '''split = endTime - startTime.
    if startTime > endTime, then need cycleLength for the calculation'''
    if startTime < endTime:
        split = endTime - startTime
    else:        
        if cycleLength != None:
            split = endTime - startTime + cycleLength
        else:
            split = None  # 如果到这里了就说明用这个函数的位置不对。周期时长无法获取，肿么回事？
    return split

def getCycleLengthOfPlanScheme(planScheme):
    '''Get cycle length, as the largest end time of all phases'''
    cycleLength = 0
    for phase in planScheme:
        endTime = helper_getSubValueFromPhase("endTime", phase)
        cycleLength = max(cycleLength, endTime)
    return cycleLength

# helper 从phase结构体中获取二级结构的字典值
def helper_getSubValueFromPhase(k, phase, getDefaultValue=False):
    phaseName = list(phase.keys())[0]
    if k == 'phaseName':
        return phaseName
    dict_defaultValues = {"lateStart": 0, "earlyCutOff": 0,
                          "allRed": 0, "greenFlash": 0,
                          "redAmber": 0, "isPermissive": 0,
                          "startTime": None, "endTime": None,
                          "startOfGreen": None, "endOfGreen": None,
                          "split": None, "greenTime": None,
                          "yellow": 3, "countDown": 9,
                          "phaseId": None, "isProhibited": 0,
                          "maxGreen": 60, "minGreen": 5,
                          "parentPhase": None, "overlapNum": None}
    # Covnert required key and phase atrributes to capital and mathch
    for key in phase[phaseName].keys():
        if key.replace(' ', '').upper() == k.replace(' ', '').upper():
            return phase[phaseName][key]
    
    # Key does not exist in the phase, return default value 
    if k not in phase[phaseName].keys() or getDefaultValue==True:
        return dict_defaultValues[k]
    # Get values of a key directly
    return phase[phaseName][k]

# helper 根据planScheme中已获取的相位，为当前的相位写入order(从1开始计数)
def helper_AssignPhaseOrder(planScheme, phaseName):
    cnt = 1
    for phase in planScheme:
        if phaseName in phase.keys():
            cnt += 1
    return cnt
    
# helper get phase attribute obj from result2 for a given phaseName and order
def helper_getPhaseInfo(phaseName, phaseOrder, result2):
    for phaseCandidate in result2:
        phaseNameCandidate = helper_getSubValueFromPhase('phaseName', phaseCandidate)
        phaseOrderCandidate = helper_getSubValueFromPhase('phaseOrder', phaseCandidate)
        if phaseNameCandidate == phaseName and phaseOrderCandidate == phaseOrder:
            return phaseCandidate
    # return None if cannot find any match
    return None

# helper: get the relationship of t and phase split(判断给定时刻与相位之间的关系)
def helper_timeIntersectsPhase(t, phase, useGreenTime=False):
    '''Four types: 0 - t=startTime; 2 - t=endTime; 1 - intersected; -1 - not intersected; -2 - not applicable
    共4种：0-等于开始时间、2-等于结束时间、1-相交、-1-不相交、-2-无法计算'''

    startTime = helper_getSubValueFromPhase("startTime", phase)
    endTime = helper_getSubValueFromPhase("endTime", phase)

    if startTime == None or endTime == None:
        return -2
    if t == startTime:
        return 0
    elif t == endTime:
        return 2
    elif startTime < endTime and (t - startTime) * (t - endTime) < 0: # 开始时间小于结束时间
        return 1
    elif startTime > endTime and (t - startTime) * (t - endTime) > 0: # 开始时间大于结束时间
        return 1
    else:
        return -1

# get Default Reference Phase List for a concurrent phase.（第八步处理redis方案时也需要）
def helper_getDefaultParentPhaseList(phaseName):
    '''return the list of default parent movements of the given ped phase; e.g.：北行人-[东直行]'''
    dict_defaultRefPhase = {'北行人': ['东直行'], '东行人': ['南直行'], '南行人': ['西直行'], '西行人': ['北直行'],
                            '北行人二次过街A': ['东直行', '西左转'], '北行人二次过街B': ['东直行', '北左转'],
                            '东行人二次过街A': ['南直行', '北左转'], '东行人二次过街B': ['南直行', '东左转'],
                            '南行人二次过街A': ['西直行', '东左转'], '南行人二次过街B': ['西直行', '南左转'],
                            '西行人二次过街A': ['北直行', '南左转'], '西行人二次过街B': ['北直行', '西左转'],
                            'NORTHPED': ['WBT'], 'EASTPED': ['NBT'], 'SOUTHPED': ['EBT'], 'WESTPED': ['SBT'],
                            'NORTHPEDA': ['WBT', 'EBL'], 'NORTHPEDB': ['WBT', 'SBL'],
                            'EASTPEDA': ['NBT', 'SBL'], 'EASTPEDB': ['NBT', 'WBL'],
                            'SOUTHPEDA': ['EBT', 'WBL'], 'SOUTHPEDB': ['EBT', 'NBL'],
                            'WESTPEDA': ['SBT', 'NBL'], 'WESTPEDB': ['SBT', 'EBL']
                           }
    if phaseName in dict_defaultRefPhase:
        return dict_defaultRefPhase[phaseName]
    else:
        return []

# helper: 判断两个相位-阶段是否相连通
def helper_twoPhaseStagesOverlapped(phase1, phase2, cycleLength): # 
    '''The two phase stages are treated as connected if their phase name and permissive are the same,
    and their truncated start and end time (by early cut off and late start) are overlapped.
    Return 1 if connected, 0 otherwise'''
    # Get info of phase1
    phaseName1 = helper_getSubValueFromPhase('phaseName', phase1)
    isPermissive1 = helper_getSubValueFromPhase('isPermissive', phase1)
    startTime1 = helper_getSubValueFromPhase('startTime', phase1)
    endTime1 = helper_getSubValueFromPhase('endTime', phase1)
    startTimeTruncated1 = startTime1 + helper_getSubValueFromPhase('lateStart', phase1)
    endTimeTruncated1 = endTime1 - helper_getSubValueFromPhase('earlyCutOff', phase1)
    # Get info of phase2
    phaseName2 = helper_getSubValueFromPhase('phaseName', phase2)
    isPermissive2 = helper_getSubValueFromPhase('isPermissive', phase2)
    startTime2 = helper_getSubValueFromPhase('startTime', phase2)
    endTime2 = helper_getSubValueFromPhase('endTime', phase2)
    startTimeTruncated2 = startTime2 + helper_getSubValueFromPhase('lateStart', phase2)
    endTimeTruncated2 = endTime2 - helper_getSubValueFromPhase('earlyCutOff', phase2)
    # Compare
    #if phaseName1 == phaseName2 and isPermissive1 == isPermissive2:  # Same name and same isPermissive
    if helper_timeIntersectsStartAndEndTime(startTimeTruncated1, startTimeTruncated2, endTimeTruncated2, cycleLength) >= 0 or\
       helper_timeIntersectsStartAndEndTime(endTimeTruncated1, startTimeTruncated2, endTimeTruncated2, cycleLength) >= 0:
        return 1
    return 0

# helper phaseName格式刷
def phaseNameFormatting(phaseNameStr):
    '''将数字或英文编号的相位名称转为标准名称（方向+流向）'''
    phaseNameStr = phaseNameStr.upper().replace(' ', '')
    dictPhaseNameStandard = {
     '北左转': ['相位1', '相位一'], '北直行': ['相位2', '相位二'],
     '东左转': ['相位3', '相位三'], '东直行': ['相位4', '相位四'],
     '南左转': ['相位5', '相位五'], '南直行': ['相位6', '相位六'],
     '西左转': ['相位7', '相位七'], '西直行': ['相位8', '相位八'],
   
     '北右转': ['相位9', '相位九'], '北掉头': ['相位13', '相位十三'],
     '东右转': ['相位10', '相位十'], '东掉头': ['相位14', '相位十四'],
     '南右转': ['相位11', '相位十一'], '南掉头': ['相位15', '相位十五'],
     '西右转': ['相位12', '相位十二'], '西掉头': ['相位16', '相位十六'],
   
     '北行人': ['相位A'], '北行人二次过街A': ['相位E'], '北行人二次过街B': ['相位F'],
     '东行人': ['相位B'], '东行人二次过街A': ['相位G'], '东行人二次过街B': ['相位H'],
     '南行人': ['相位C'], '南行人二次过街A': ['相位I'], '南行人二次过街B': ['相位J'],
     '西行人': ['相位D'], '西行人二次过街A': ['相位K'], '西行人二次过街B': ['相位L'],
                       
     'SBL': ['PHASEONE', 'PHASE1'], 'SBT': ['PHASETWO', 'PHASE2'],
     'WBL': ['PHASETHREE', 'PHASE3'], 'WBT': ['PHASEFOUR', 'PHASE4'],
     'NBL': ['PHASEFIVE', 'PHASE5'], 'NBT': ['PHASESIX', 'PHASE6'],
     'EBL': ['PHASESEVEN', 'PHASE7'], 'EBT': ['PHASEEIGHT', 'PHASE8'],
       
     'SBR': ['PHASENINE', 'PHASE9'], 'SBU': ['PHASETHIRTEEN', 'PHASE13'],
     'WBR': ['PHASETEN', 'PHASE10'], 'WBU': ['PHASEFOURTEEN', 'PHASE14'],
     'NBR': ['PHASEELEVEN', 'PHASE11'], 'NBU': ['PHASEFIFTEEN', 'PHASE15'],
     'EBR': ['PHASETWELVE', 'PHASE12'], 'EBU': ['PHASESIXTEEN', 'PHASE16'],
     
     'NORTHPED': ['PHASEA'], 'NORTHPEDA': ['PHASEE'], 'NORTHPEDB': ['PHASEF'],
     'EASTPED': ['PHASEB'], 'EASTPEDA': ['PHASEG'], 'EASTPEDB': ['PHASEH'],
     'SOUTHPED': ['PHASEC'], 'SOUTHPEDA': ['PHASEI'], 'SOUTHPEDB': ['PHASEJ'],
     'WESTPED': ['PHASED'], 'WESTPEDA': ['PHASEK'], 'WESTPEDB': ['PHASEL'],
     }
    if phaseNameStr in dictPhaseNameStandard:
        return phaseNameStr  # The raw phase name is already standard
   
    phaseNameStandard = phaseNameStr # default output is the raw str
    for k in dictPhaseNameStandard:
        if phaseNameStr in dictPhaseNameStandard[k]:
            phaseNameStandard = k
            break
    return phaseNameStandard
    
# 【Step 5】helper functions 
# For plan conflict phase validation and drawing phase diagram

def helper_areConflictingPhasesTimedSimultaneously(phaseName, phaseConflictName, lightStateOfPhase, lightStateOfPhaseConflict):
    '''根据灯色序列，识别出phaseName和phaseConflictName这两个相位是否存在冲突放行的时段。'''
    dictOpposite = {'东': '西', '西': '东', '北': '南', '南': '北', 'E': 'W', 'W': 'E', 'N': 'S', 'S': 'N'}
    res = []  # conflicted intervals, list of list
    startOfCurInterval = None
    for t in range(0, len(lightStateOfPhase)):
        flagOfConclictedPhasesTimedSimultaneouslyAtT = False
        colorCodes = [lightStateOfPhase[t], lightStateOfPhaseConflict[t]] # collect the color code of the two phases at time t
        if all([_ != 0 for _ in colorCodes]) == True:
            flagOfConclictedPhasesTimedSimultaneouslyAtT = True
        # 特殊处理直行和对面允许型左转的情况
        if '直行' in phaseName and '左转' in phaseConflictName and dictOpposite[phaseName[0]] == phaseConflictName[0]:
            if lightStateOfPhaseConflict[t] == -1 or lightStateOfPhaseConflict[t] == 1:
                flagOfConclictedPhasesTimedSimultaneouslyAtT = False # [phaseName: through] and [phaseConflictName: opposite left-turn]
        if '左转' in phaseName and '直行' in phaseConflictName and dictOpposite[phaseName[0]] == phaseConflictName[0]:
            if lightStateOfPhase[t] == -1 or lightStateOfPhase[t] == 1:
                flagOfConclictedPhasesTimedSimultaneouslyAtT = False # [phaseName: left-turn] and [phaseConflictName: opposite through] 
        # Special case for through conflicting with opposing permissive left turn
        if 'BT' in phaseName and 'BL' in phaseConflictName and dictOpposite[phaseName[0]] == phaseConflictName[0]:
            if lightStateOfPhaseConflict[t] == -1 or lightStateOfPhaseConflict[t] == 1:
                flagOfConclictedPhasesTimedSimultaneouslyAtT = False # [phaseName: through] and [phaseConflictName: opposite left-turn]
        if 'BL' in phaseName and 'BT' in phaseConflictName and dictOpposite[phaseName[0]] == phaseConflictName[0]:
            if lightStateOfPhase[t] == -1 or lightStateOfPhase[t] == 1:
                flagOfConclictedPhasesTimedSimultaneouslyAtT = False # [phaseName: left-turn] and [phaseConflictName: opposite through] 

        
        if flagOfConclictedPhasesTimedSimultaneouslyAtT:  # timed simultaneously at time t
            if startOfCurInterval == None:
                startOfCurInterval = t
                endOfCurInterval = t+1
            else:
                endOfCurInterval = t+1
        else:                                            # not timed simultaneously at time t
            if startOfCurInterval == None:
                pass
            else:
                res.append([startOfCurInterval, endOfCurInterval])
                startOfCurInterval = None
                endOfCurInterval = None
                
    # Final upate at the end
    if startOfCurInterval != None:
        res.append([startOfCurInterval, endOfCurInterval])
        
    return res

# Check WALK interval of ped phases, and give warning msg if shorter than 7s
def checkPedWalkIntvl(dict_lightColorRec):
    '''
    Example: {"南行人": [2,1,1,2,2,2,2,2,2,2,2,2,1,1,2]} -> {'南行人 WALK too short': [2]}
    '''
    res = {} # record ped phases with WALK interval smaller than 7s
    for phaseName in dict_lightColorRec:
        if '行人' not in phaseName and 'Ped' not in phaseName:
            continue
        # Get a list of the walk interval duration of the ped phase
        listOfWalk = []
        countOfWalk = 0
        
        for t in range(len(dict_lightColorRec[phaseName])):
            if dict_lightColorRec[phaseName][t] == 2:
                countOfWalk += 1
            else:
                if countOfWalk > 0:
                    listOfWalk.append(countOfWalk)
                    countOfWalk = 0
        # The last timepoint
        if countOfWalk > 0:
            listOfWalk.append(countOfWalk)
            countOfWalk = 0
        
        # Check if a walk interval crosses the end of the cycle
        if dict_lightColorRec[phaseName][0] == 2 and dict_lightColorRec[phaseName][-1] == 2:
            listOfWalk[0] = listOfWalk[0] + listOfWalk[-1]
            listOfWalk = listOfWalk[0:-1]            
        
        # Derive the list of walk interval that are too short
        listOfWalkShort = [_ for _ in listOfWalk if _ < 7 ]
        
        # Record the warning info
        if len(listOfWalkShort) > 0:
            res.update({phaseName + ' WALK too short': listOfWalkShort})
        #print(listOfWalkShort, listOfWalk)   
    return res

# fontsize modifier
def calcFontsizeModifier(figH, N):
    '''figH - the height of the figure
    N - the number of bars'''
    actualHeightOfBar = figH / N
    if actualHeightOfBar < 0.8:  # 8 / 10
        return 0.75
    elif actualHeightOfBar > 1:  # 8 / 8
        return 1.25
    elif actualHeightOfBar > 2:  # 8 / 4
        return 1.5
    else:
        return 1

# symbol and label of each phase
def getPhasePlotLabelAndRotation(phaseName):
    '''根据相位的中文名称获取其画图的text符号和旋转角度，中文或英文两种模式'''
    dict_phaseNameLabelAndRotation = {
    '北直行': ['↓', 0], '北左转': ['↳', 0],'北右转': ['↲', 0], '北掉头': ['↺', 0],
    '东直行': ['↓', -90], '东左转': ['↳', -90],'东右转': ['↲', -90], '东掉头': ['↺', -90],
    '南直行': ['↓', 180], '南左转': ['↳', 180],'南右转': ['↲', 180], '南掉头': ['↺', 180],                                                  
    '西直行': ['↓', 90], '西左转': ['↳', 90],'西右转': ['↲', 90], '西掉头': ['↺', 90],
        
    '北行人': ['↔', 0], '东行人': ['↔', 90], '南行人': ['   ↕', -90], '西行人': ['↔', -90],
    '北行人二次过街A': ['↔', 0], '东行人二次过街A': ['↔', 90], '南行人二次过街A': ['   ↕', -90], '西行人二次过街A': ['↔', -90],
    '北行人二次过街B': ['↔', 0], '东行人二次过街B': ['↔', 90], '南行人二次过街B': ['   ↕', -90], '西行人二次过街B': ['↔', -90],
        
    'SBT': ['↓', 0], 'SBL': ['↳', 0],'SBR': ['↲', 0], 'SBU': ['↺', 0],
    'WBT': ['↓', -90], 'WBL': ['↳', -90],'WBR': ['↲', -90], 'WBU': ['↺', -90],
    'NBT': ['↓', 180], 'NBL': ['↳', 180],'NBR': ['↲', 180], 'NBU': ['↺', 180],                                                  
    'EBT': ['↓', 90], 'EBL': ['↳', 90],'EBR': ['↲', 90], 'EBU': ['↺', 90],
        
    'NORTHPED': ['↔', 0], 'EASTPED': ['↔', 90], 'SOUTHPED': ['   ↕', -90], 'WESTPED': ['↔', -90],
    'NORTHPEDA': ['↔', 0], 'EASTPEDA': ['↔', 90], 'SOUTHPEDA': ['   ↕', -90], 'WESTPEDA': ['↔', -90],
    'NORTHPEDB': ['↔', 0], 'EASTPEDB': ['↔', 90], 'SOUTHPEDB': ['   ↕', -90], 'WESTPEDB': ['↔', -90]
    }
    if phaseName in dict_phaseNameLabelAndRotation:
        return dict_phaseNameLabelAndRotation[phaseName]
    
    return ['', 0]

# draw rectangle
def drawRectangleInCycle(ax, t1, width, y1, height, cycleLength, color):
    '''draw rectangle within cycle. t1->t2, or 0->t2 + t1 -> cycleLength,
    y1-y coord of the anchor point， width = t2-t1'''
    t2 = (t1 + width) % cycleLength
    if width == 0:#t1 == t2:
        return
    if t1 < t2:  # 周期内的长方形
        ax.add_patch(Rectangle((t1, y1), t2-t1, height, color=color, ec = 'k'))
    else:  # 跨周期的两个长方形
        if cycleLength-t1 > 0:  # avoid drawing a rectangle of width zero (which is plotted as a line)
            ax.add_patch(Rectangle((t1, y1), cycleLength-t1, height, color=color, ec = 'k'))
        if t2 > 0:              # avoid drawing a rectangle of width zero (which is plotted as a line)
            ax.add_patch(Rectangle((0, y1), t2, height, color=color, ec = 'k'))

# helper: paint light color in the given interval along a cycle
def helper_paintLightColor(listToPaint, startTime, duration, cycleLength, colorCode):
    '''From startTime, paint colorCode for a length of duration, with the consideration of the interval extends beyond cycleLength'''
    if startTime + duration <= cycleLength:
        listToPaint[startTime:startTime+duration] = [colorCode] * duration
    else:
        listToPaint[startTime:cycleLength] = [colorCode] * (cycleLength-startTime)
        listToPaint[0:duration-(cycleLength-startTime)] = [colorCode] * (duration-(cycleLength-startTime))
    return listToPaint