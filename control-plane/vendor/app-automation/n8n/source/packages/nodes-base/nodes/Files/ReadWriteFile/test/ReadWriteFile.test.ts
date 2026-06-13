import { NodeTestHarness } from '@nodes-testing/node-test-harness';
import fsPromises from 'fs/promises';
import type { WorkflowTestData } from 'n8n-workflow';

describe('Test ReadWriteFile Node', () => {
	const directory = __dirname.replace(/\\/gi, '/');

	const testHarness = new NodeTestHarness();
	const workflowData = testHarness.readWorkflowJSON('ReadWriteFile.workflow.json');

	const readFileNode = workflowData.nodes.find((n) => n.name === 'Read from Disk')!;
	readFileNode.parameters.fileSelector = `${directory}/image.jpg`;

	const writeFileNode = workflowData.nodes.find((n) => n.name === 'Write to Disk')!;
	writeFileNode.parameters.fileName = `${testHarness.temporaryDir}/image-written.jpg`;

	beforeEach(() => {
		jest.spyOn(fsPromises, 'realpath').mockImplementation(async (path) => path as string);
	});

	const tests: WorkflowTestData[] = [
		{
			description: 'nodes/Files/ReadWriteFile/test/ReadWriteFile.workflow.json',
			input: {
				workflowData,
			},
			output: {
				assertBinaryData: true,
				nodeData: {
					'Read from Disk': [
						[
							{
								json: {
									fileExtension: 'jpg',
									fileName: 'image.jpg',
									fileSize: '1.04 kB',
									fileType: 'image',
									mimeType: 'image/jpeg',
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
					'Write to Disk': [
						[
							{
								json: {
									fileExtension: 'jpg',
									fileName: writeFileNode.parameters.fileName,
									fileSize: '1.04 kB',
									fileType: 'image',
									mimeType: 'image/jpeg',
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
