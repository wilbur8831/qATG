import numpy as np
from copy import deepcopy
from qiskit import Aer
from qiskit import execute
from qiskit import transpile, QuantumRegister, ClassicalRegister, QuantumCircuit
from qiskit.circuit import Parameter
import qiskit.circuit.library as qGate

from qatgFault import qatgFault
from qatgUtil import U3, CNOT

INT_MIN = 1E-100

class qatg():
	def __init__(self, circuitSize: int = None, basisGateSet: list[qGate], couplingMap: list[list], \
			quantumRegisterName: str = 'q', classicalRegisterName: str = 'c', \
			targetAlpha: float = 0.99, targetBeta: float = 0.999, \
			gridSlice: int = 21, \
			gradientDescentSearchTime: int = 800, gradientDescentStep: float = 0.01, \
			maxTestTemplateSize: int = 50, minRequiredEffectSize: float = 3, \
			testSampleTime: int = 10000):
		if not isinstance(circuitSize, int):
			raise TypeError('circuitSize must be int')
		if circuitSize <= 0:
			raise ValueError('circuitSize must be positive')
		
		# list[qGate]
		self.basisGateSet = basisGateSet
		self.couplingMap = couplingMap
		self.quantumRegisterName = quantumRegisterName
		self.classicalRegisterName = classicalRegisterName
		self.targetAlpha = targetAlpha
		self.targetBeta = targetBeta
		self.gridSlice = gridSlice
		self.gradientDescentSearchTime = gradientDescent
		self.gradientDescentStep = gradientDescentStep
		self.maxTestTemplateSize = maxTestTemplateSize
		self.minRequiredEffectSize = minRequiredEffectSize
		self.testSampleTime = testSampleTime

		self.quantumRegister = QuantumRegister(self.circuitSize, self.quantumRegisterName)
		self.classicalRegister = ClassicalRegister(self.circuitSize, self.classicalRegisterName)
		self.backend = Aer.get_backend('qasm_simulator')
		self.basisGateSetString = [gate.__name__[:-4].lower() for gate in self.basisGateSet]
		q = QuantumCircuit(1)
		self.qiskitParameterTheta = Parameter('theta')
		self.qiskitParameterPhi = Parameter('phi')
		self.qiskitParameterLambda = Parameter('lam')
		q.u(self.qiskitParameterTheta, self.qiskitParameterPhi, self.qiskitParameterLambda, 0)
		try:
			self.effectiveUGateCircuit = transpile(q, basis_gates = self.basisGateSetString, optimization_level = 3)
		except Exception as e:
			raise e
		return

	def getTestConfiguration(self, singleFaultList, twoFaultList, \
			singleInitialState: np.array = np.array([1, 0]), twoInitialState: array = np.array([1, 0, 0, 0]), simulateConfiguration: bool = True):
		# simulateConfiguration: True, simulate the configuration and generate test repetition
		# false: don't simulate and repetition = NaN

		# singleFaultList: a list of singleFault
		# singleFault: a class object inherit class Fault
		# gateType: faultObject.getGateType()
		# original gate parameters: faultObject.getOriginalGateParameters()
		# faulty: faultObject.getFaulty(faultfreeParameters)

		configurationList = []

		for singleFault in singleFaultList:
			if not issubclass(singleFault, qatgFault):
				raise TypeError(f"{singleFault} should be subclass of qatgFault")
			template = self.generateTestTemplate(faultObject = singleFault, initialState = singleInitialState, findActivationGate = findSingleElement)
				

		for twoFault in twoFaultList:
			if not issubclass(singleFault, qatgFault):
				raise TypeError(f"{twoFault} should be subclass of qatgFault")
			template = self.generateTestTemplate(faultObject = twoFault, initialState = twoInitialState, findActivationGate = findTwoElement)

		pass

	def getTestTemplate(self, faultObject, initialState, findActivationGate):
		templateGateList = [] # list of qGate

		faultyQuantumState = deepcopy(initialState)
		faultfreeQuantumState = deepcopy(initialState)

		for element in range(self.maxTestTemplateSize):
			newElement, faultyQuantumState, faultfreeQuantumState = findActivationGate(faultObject = faultObject, faultyQuantumState = faultyQuantumState, faultfreeQuantumState = faultfreeQuantumState)
			# newElement: list[np.array(gate)]
			templateGateList.append(newElement)
			effectSize = calEffectSize(faultyQuantumState, faultfreeQuantumState)
			if effectsize > self.minRequiredEffectSize:
				break

		return templateGateList

	def findSingleElement(self, faultObject, faultyQuantumState, faultfreeQuantumState):
		# optimize activation gate
		optimalParameterList = self.singleActivationOptimization(faultyQuantumState, faultfreeQuantumState, faultObject)
		newElement = U2GateSetsTranspile(optimalParameterList) # a list of qGate
		newElement.append(faultObject.getOriginalGate())
		return newElement

	def singleActivationOptimization(self, faultyQuantumState, faultfreeQuantumState, faultObject):
		originalGateParameters = faultObject.getOriginalGateParameters() # list of parameters
		originalGateMatrix = faultObject.getOriginalGate().to_matrix()
		faultyGateMatrix = faultObject.getFaulty(originalGateParameters).to_matrix() # np.array(gate)

		def score(parameters):
			return vectorDistance(
				matrixOperation([U3(parameters), originalGateMatrix], faultfreeQuantumState), 
				matrixOperation(np.concatenate([insertFault2GateList(U2GateSetsTranspile(parameters), faultObject), [faultyGateMatrix]]), faultyQuantumState))

		results = []
		for theta in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
			for phi in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
				for lam in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
					results.append([[theta, phi, lam], score([theta, phi, lam])])
		parameterList = max(results, key = lambda x: x[1])[0]

		for time in range(self.gradientDescentSearchTime):
			newParameterList = [0]*len(parameterList)
			for i in range(len(parameterList)):
				currentScore = score(parameterList)
				parameterList[i] += self.gradientDescentStep
				upScore = score(parameterList)
				parameterList[i] -= 2*self.gradientDescentStep
				downScore = score(parameterList)
				parameterList[i] += self.gradientDescentStep

				if(upScore > currentScore and upScore >= downScore):
					newParameterList[i] += self.gradientDescentStep
				elif(downScore > currentScore and downScore >= upScore):
					newParameterList[i] -= self.gradientDescentStep
				elif upScore == currentScore == downScore:
					newParameterList[i] += self.gradientDescentStep
			if newParameterList == [0, 0, 0]:
				break
			for i in range(len(parameterList)):
				parameterList[i] += newParameterList[i]

		return parameterList

	def findTwoElement(self, faultObject, faultyQuantumState, faultfreeQuantumState):
		originalGateParameters = faultObject.getOriginalGateParameters()
		originalGateMatrix = faultObject.getOriginalGate().to_matrix()
		faultyGateMatrix = faultObject.getFaultyGate(originalGateParameters).to_matrix() # np.array(gate)
		
		optimalParameterList = self.twoActivationOptimization(faultyQuantumState, faultfreeQuantumState, faultObject)
		aboveActivationGate = U2GateSetsTranspile(optimalParameterList[0:3])
		belowActivationGate = U2GateSetsTranspile(optimalParameterList[3:6])
		toalActivationGate = [[aboveGate, belowGate] for aboveGate, belowGate in zip(aboveActivationGate, belowActivationGate)]
		toalActivationGate.append(originalGateMatrix)
		return toalActivationGate

	def twoActivationOptimization(self, faultyQuantumState, faultfreeQuantumState, faultObject):
		# for only CNOT have fault
		def score(parameters):
			return vectorDistance(
				matrixOperation([U3(parameters[0:3]), U3(parameters[3:6]), originalGateMatrix], faultfreeQuantumState), 
				matrixOperation([U3(parameters[0:3]), U3(parameters[3:6]), faultyGateMatrix], faultyQuantumState))

		# 3+3 method
		results = []
		for theta in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
			for phi in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
				for lam in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
					results.append([[theta, phi, lam], score([theta, phi, lam, 0, 0, 0])])
		first_three = max(results, key = lambda x: x[1])[0]

		results = []
		for theta in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
			for phi in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
				for lam in np.linspace(-np.pi, np.pi, num=self.gridSlice, endpoint = True):
					results.append([[theta, phi, lam], score(first_three + [theta, phi, lam])])
		next_three = max(results, key = lambda x: x[1])[0]
	
		parameterList = np.concatenate([first_three, next_three])

		for time in range(self.gradientDescentSearchTime):
			newParameterList = [0]*len(parameterList)
			for i in range(len(parameterList)):
				currentScore = score(parameterList)
				parameterList[i] += self.gradientDescentStep
				upScore = score(parameterList)
				parameterList[i] -= 2*self.gradientDescentStep
				downScore = score(parameterList)
				parameterList[i] += self.gradientDescentStep

				if(upScore > currentScore and upScore >= downScore):
					newParameterList[i] += self.gradientDescentStep
				elif(downScore > currentScore and downScore >= upScore):
					newParameterList[i] -= self.gradientDescentStep
				elif upScore == currentScore == downScore:
					newParameterList[i] += self.gradientDescentStep
			if newParameterList == [0, 0, 0, 0, 0, 0]:
				break
			for i in range(len(parameterList)):
				parameterList[i] += newParameterList[i]

		return parameterList

	@staticmethod
	def calEffectSize(faultyQuantumState, faultfreeQuantumState):
		deltaSquare = np.square(faultyQuantumState - faultfreeQuantumState)
		effectSize = np.sum(delta_square / (faultyQuantumState + INT_MIN))
		effectSize = np.sqrt(effectSize)
		if effectSize < 0.1:
			effectSize = 0.1
		return effectSize

	@staticmethod
	def U2GateSetsTranspile(UParameters):
		# to gate list directly
		resultCircuit = self.effectiveUGateCircuit.bind_parameters({self.qiskitParameterTheta: UParameters[0], \
			self.qiskitParameterPhi: UParameters[1], self.qiskitParameterLambda: UPartParameters[2]})
		return [gate for gate, _, _ in resultCircuit.data] # a list of qGate

	@staticmethod
	def insertFault2GateList(gateList, faultObject):
		return [faultObject.getFaulty(gate.params).to_matrix() if isinstance(gate, faultObject.getGateType()) else gate.to_matrix() for gate in gateList]
		