import React, { Fragment } from 'react';
import { Listbox, Transition } from '@headlessui/react';
import { CheckIcon, ChevronUpDownIcon, ServerIcon } from '@heroicons/react/20/solid';

interface ServerSelectorProps {
  servers: string[];
  selectedServer: string | null;
  onServerChange: (server: string | null) => void;
}

export default function ServerSelector({ servers, selectedServer, onServerChange }: ServerSelectorProps) {
  // Add "All Servers" as the first option
  const options = [
    { id: null, name: 'All Servers' },
    ...servers.map(server => ({ id: server, name: server }))
  ];

  const selected = options.find(opt => opt.id === selectedServer) || options[0];

  return (
    <div className="w-64">
      <Listbox value={selected} onChange={(option) => onServerChange(option.id)}>
        <div className="relative mt-1">
          <Listbox.Button className="relative w-full cursor-default rounded-lg bg-white/10 py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus-visible:border-indigo-500 focus-visible:ring-2 focus-visible:ring-white/75 focus-visible:ring-offset-2 focus-visible:ring-offset-orange-300 sm:text-sm backdrop-blur-md border border-white/20 text-white hover:bg-white/20 transition-colors">
            <span className="flex items-center truncate">
              <ServerIcon className="mr-2 h-5 w-5 text-gray-400" aria-hidden="true" />
              <span className="block truncate">{selected.name}</span>
            </span>
            <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
              <ChevronUpDownIcon
                className="h-5 w-5 text-gray-400"
                aria-hidden="true"
              />
            </span>
          </Listbox.Button>
          <Transition
            as={Fragment}
            leave="transition ease-in duration-100"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <Listbox.Options className="absolute mt-1 max-h-60 w-full overflow-auto rounded-md bg-slate-800 py-1 text-base shadow-lg ring-1 ring-black/5 focus:outline-none sm:text-sm z-50 border border-white/10">
              {options.map((option, personIdx) => (
                <Listbox.Option
                  key={personIdx}
                  className={({ active }) =>
                    `relative cursor-default select-none py-2 pl-10 pr-4 ${
                      active ? 'bg-indigo-500/20 text-indigo-300' : 'text-gray-300'
                    }`
                  }
                  value={option}
                >
                  {({ selected }) => (
                    <>
                      <span
                        className={`block truncate ${
                          selected ? 'font-medium text-white' : 'font-normal'
                        }`}
                      >
                        {option.name}
                      </span>
                      {selected ? (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-indigo-400">
                          <CheckIcon className="h-5 w-5" aria-hidden="true" />
                        </span>
                      ) : null}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </Transition>
        </div>
      </Listbox>
    </div>
  );
}
