import { NodeTestHarness } from '@nodes-testing/node-test-harness';
import fsPromises from 'fs/promises';
import type { WorkflowTestData } from 'n8n-workflow';
import path from 'path';

describe('Test Write Binary File Node', () => {
	const testHarness = new NodeTestHarness();
	const workflowData = testHarness.readWorkflowJSON('WriteBinaryFile.workflow.json');
	const readFileNode = workflowData.nodes.find((n) => n.name === 'Read Binary File')!;
	readFileNode.parameters.filePath = path.join(__dirname, 'image.jpg');

	const writeFileNode = workflowData.nodes.find((n) => n.name === 'Write Binary File')!;
	const writeFilePath = path.join(testHarness.temporaryDir, 'image-written.jpg');
	writeFileNode.parameters.fileName = writeFilePath;

	beforeEach(() => {
		jest.spyOn(fsPromises, 'realpath').mockImplementation(async (path) => path as string);
	});

	const tests: WorkflowTestData[] = [
		{
			description: 'nodes/WriteBinaryFile/test/WriteBinaryFile.workflow.json',
			input: {
				workflowData,
			},
			output: {
				assertBinaryData: true,
				nodeData: {
					'Write Binary File': [
						[
							{
								json: {
									fileName: writeFilePath,
								},
								binary: {
									data: {
										mimeType: 'image/jpeg',
										fileType: 'image',
										fileExtension: 'jpg',
										data: '/9j/4AAQSkZJRgABAQEASABIAAD/4QBmRXhpZgAATU0AKgAAAAgABAEaAAU<ssh-key>',
										fileName: 'image.jpg',
										fileSize: '1.04 kB',
									},
								},
							},
						],
					],
				},
			},
		},
	];

	for (const testData of tests) {
		testHarness.setupTest(testData);
	}
});
