import { NodeTestHarness } from '@nodes-testing/node-test-harness';
import type { WorkflowTestData } from 'n8n-workflow';
import path from 'path';

describe('Test Read Binary File Node', () => {
	const testHarness = new NodeTestHarness();
	const workflowData = testHarness.readWorkflowJSON('ReadBinaryFile.workflow.json');
	const node = workflowData.nodes.find((n) => n.name === 'Read Binary File')!;
	node.parameters.filePath = path.join(__dirname, 'image.jpg');

	const tests: WorkflowTestData[] = [
		{
			description: 'nodes/ReadBinaryFile/test/ReadBinaryFile.workflow.json',
			input: {
				workflowData,
			},
			output: {
				assertBinaryData: true,
				nodeData: {
					'Read Binary File': [
						[
							{
								json: {},
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
