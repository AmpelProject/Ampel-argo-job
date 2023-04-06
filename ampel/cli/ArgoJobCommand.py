#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File:                Ampel-core/ampel/cli/ArgoJobCommand.py
# License:             BSD-3-Clause
# Author:              jvs
# Date:                2022
# Last Modified Date:  02.04.2023
# Last Modified By:    valery brinnel <firstname.lastname@gmail.com>

import sys, signal, tempfile, requests, tarfile, os, ujson
from multiprocessing import Queue, Process
from typing import Any
from ampel.abstract.AbsEventUnit import AbsEventUnit
from ampel.model.UnitModel import UnitModel
from ampel.struct.Resource import Resource
from ampel.core.EventHandler import EventHandler
from ampel.log.AmpelLogger import AmpelLogger
from ampel.log.LogFlag import LogFlag
from ampel.cli.JobCommand import JobCommand, run_mp_process, signal_handler
from ampel.core.AmpelContext import AmpelContext
from ampel.model.job.ArgoJobModel import ArgoJobModel
from ampel.model.job.InputArtifact import InputArtifact
from ampel.model.job.TaskUnitModel import TaskUnitModel
from ampel.model.job.TemplateUnitModel import TemplateUnitModel


class ArgoJobCommand(JobCommand):

	def get_cli_op_name(self) -> str:
		return "ajob"

	def run_tasks(self, # type: ignore[override]
		ctx: AmpelContext,
		job: ArgoJobModel,
		jtasks: list[dict[str, Any]],
		schema_descr: str,
		logger: AmpelLogger
	) -> list[int]:

		run_ids = []
		for i, taskd in enumerate(jtasks):

			process_name = f'{job.name or schema_descr}#{i}'

			if 'title' in taskd:
				self.print_chapter(taskd['title'] if taskd.get('title') else f'Task #{i}', logger)
				#process_name += f' [{taskd['title']}]'
				del taskd['title']
			elif i != 0:
				self.print_chapter(f'Task #{i}', logger)

			if (expand_with := job.task[i].expand_with) is not None:

				try:

					process_queues: list[Process] = []
					result_queues: list[Any] = []

					signal.signal(signal.SIGINT, signal_handler)
					signal.signal(signal.SIGTERM, signal_handler)

					for item in expand_with:

						self._fetch_inputs(job, job.task[i], item, logger)

						result_queue: Queue = Queue()
						resource_queue: Queue[Resource] = Queue()
						p = Process(
							target = run_mp_process,
							args = (
								result_queue,
								resource_queue,
								ctx.config._config,
								job.resolve_expressions(
									taskd,
									job.task[i],
									item
								),
								process_name,
							),
							daemon = True,
						)
						p.start()
						process_queues.append(p)
						result_queues.append(result_queue)
					
					for i, (p, r1) in enumerate(zip(process_queues, result_queues)):
						p.join()
						if (m := r1.get()):
							logger.info(f'{taskd["unit"]}#{i} return value: {m}')

				except KeyboardInterrupt:
					sys.exit(1)
			
			else:
				
				self._fetch_inputs(job, job.task[i], None, logger)

				proc = ctx.loader.new_context_unit(
					model = UnitModel(**job.resolve_expressions(taskd, job.task[i])),
					context = ctx,
					process_name = process_name,
					job_sig = job.sig,
					sub_type = AbsEventUnit,
					base_log_flag = LogFlag.MANUAL_RUN
				)

				event_hdlr = EventHandler(
					proc.process_name,
					ctx.get_database(),
					raise_exc = proc.raise_exc,
					job_sig = job.sig,
					extra = {'task': i}
				)

				x = proc.run(event_hdlr)
				if event_hdlr.run_id:
					run_ids.append(event_hdlr.run_id)

				logger.info(f'{taskd["unit"]} return value: {x}')

		return run_ids


	def get_task_dict(self, task_model) -> dict[str, Any]:
		return task_model.dict(
			exclude={'inputs', 'outputs', 'expand_with'},
			exclude_unset=True
		)


	def get_job_dict(self, job, jtasks: list[dict[str, Any]]) -> dict[str, Any]:
		return ujson.loads(
			ArgoJobModel(
				**(
					job.dict(exclude_unset=True) | # type: ignore[arg-type]
					{
						'task': [
							td | task.dict(
								include={'inputs', 'outputs', 'expand_with', 'title'},
								exclude_unset=True
							)
							for task, td in zip(job.task, jtasks)
						]
					}
				)
			).json(exclude_unset=True)
		)


	@staticmethod
	def _fetch_inputs(
		job: ArgoJobModel,
		task: TaskUnitModel | TemplateUnitModel,
		item: None | str | dict | list,
		logger: AmpelLogger,
	):
		"""
		Ensure that input artifacts exist
		"""
		for artifact in task.inputs.artifacts:

			resolved_artifact = InputArtifact(
				**job.resolve_expressions(
					ujson.loads(artifact.json()), task, item
				)
			)

			if resolved_artifact.path.exists():
				logger.info(f'Artifact {resolved_artifact.name} exists at {resolved_artifact.path}')
			else:
				logger.info(
					f'Fetching artifact {resolved_artifact.name} from '
					f'{resolved_artifact.http.url} to {resolved_artifact.path}'
				)
				os.makedirs(resolved_artifact.path.parent, exist_ok=True)
				with tempfile.NamedTemporaryFile(delete=False) as tf:
					r = requests.get(resolved_artifact.http.url, stream=True)
					r.raise_for_status()
					for chunk in r.iter_content(chunk_size=1<<13): # noqa
						tf.write(chunk)
					tf.flush()
					try:
						with tarfile.open(tf.name) as archive:
							logger.info(f'{resolved_artifact.name} is a tarball; extracting')
							os.makedirs(resolved_artifact.path)
							archive.extractall(resolved_artifact.path)
						os.unlink(tf.name)
					except tarfile.ReadError:
						os.rename(tf.name, resolved_artifact.path)
