import kopf
from collections import defaultdict
import time

import util
from util import parse_gvr, spaced_name, parse_spaced_name

"""
An embedded meta-actor that implements the mount semantics.

Event watch:
- Watch the parent model and identify the child models;
- Watch the child models;

Event propagation:
- On child's updates (intent and status): propagate to the child's 
  copy in the parent;
- On parent's updates (intent) on the child's copy: propagate to 
  the child's intent;
"""


class Watch:
    def __init__(self, g, v, r, n, ns="default", *,
                 create_fn=None,
                 resume_fn=None,
                 update_fn=None,
                 # TBD enable finalizer but avoid looping with multiple children
                 delete_fn=None, delete_optional=True,
                 field_fn=None, field=""):
        self._registry = util.KopfRegistry()
        _args = (g, v, r)
        _kwargs = {
            "registry": self._registry,
            # watch a specific model only
            "when": lambda name, namespace, **_: name == n and namespace == ns,
        }
        if create_fn is not None:
            kopf.on.create(*_args, **_kwargs)(create_fn)
        if resume_fn is not None:
            kopf.on.resume(*_args, **_kwargs)(resume_fn)
        if update_fn is not None:
            kopf.on.update(*_args, **_kwargs)(update_fn)
        if delete_fn is not None:
            kopf.on.delete(*_args, **_kwargs, optional=delete_optional)(delete_fn)
        if field_fn is not None and field != "":
            kopf.on.field(field=field, *_args, **_kwargs)(field_fn)
        assert create_fn or resume_fn or update_fn or delete_fn, "no handler provided"

        self._ready_flag, self._stop_flag = None, None

    def start(self):
        self._ready_flag, self._stop_flag = util.run_operator(self._registry)
        return self

    def stop(self):
        assert self._stop_flag, "watch has not started"
        self._stop_flag.set()
        return self


class Mounter:
    """Implements the mount semantics for a given (parent) digivice"""

    def __init__(self, g, v, r, n, ns="default"):

        """ children event handlers """

        def on_child_create(body, *args, **kwargs):
            _, _ = args, kwargs
            _g, _v, _r = util.gvr_from_body(body)
            _sync_from_parent(_g, _v, _r,
                              attrs_to_trim={"status", "output", "obs"},
                              *args, **kwargs)
            _sync_to_parent(_g, _v, _r,
                            attrs_to_trim={"intent", "input"},
                            *args, **kwargs)

        def on_child_update(body, meta, name, namespace,
                            *args, **kwargs):
            _, _ = args, kwargs

            _g, _v, _r = util.gvr_from_body(body)
            _id = util.model_id(_g, _v, _r, name, namespace)

            if meta["generation"] == self._children_gen[_id] + 1:
                return

            return _sync_to_parent(_g, _v, _r, name, namespace, meta,
                                   *args, **kwargs)

        def on_child_delete(body, name, namespace,
                            *args, **kwargs):
            _, _ = args, kwargs

            _g, _v, _r = util.gvr_from_body(body)

            # remove watch
            gvr_str = util.gvr(_g, _v, _r)
            nsn_str = util.spaced_name(name, namespace)

            w = self._children_watches.get(gvr_str, {}).get(nsn_str, None)
            if w is not None:
                w.stop()
                self._children_watches[gvr_str].pop(nsn_str, "")

            # will delete from parent
            _sync_to_parent(_g, _v, _r, name, namespace, spec=None,
                            *args, **kwargs)

        def _sync_from_parent(group, version, plural, name, namespace, meta,
                              attrs_to_trim=None, *args, **kwargs):
            _, _ = args, kwargs

            parent, prv, pgn = util.get_spec(g, v, r, n, ns)

            # check if child exists
            mounts = parent.get("mount", {})
            gvr_str = util.gvr(group, version, plural)
            nsn_str = util.spaced_name(name, namespace)

            if (gvr_str not in mounts or
                    (nsn_str not in mounts[gvr_str] and
                     name not in mounts[gvr_str])):
                print(f"unable to find the {nsn_str} or {name} in the {parent}")
                return

            models = mounts[gvr_str]
            n_ = name if name in models else nsn_str

            patch = models[n_]
            if attrs_to_trim is not None:
                patch = util.trim_attr(patch, attrs_to_trim)

            e = util.patch_spec(group, version, plural, name, namespace, patch,
                                rv=models[n_].get("version", meta["resourceVersion"]))

            if e is not None:
                print(f"mounter: unable to sync from parent due to {e}")
            else:
                self._children_gen[util.model_id(group, version, plural,
                                                 name, namespace)] = meta["generation"]

        def _sync_to_parent(group, version, plural, name, namespace, meta,
                            spec, diff, attrs_to_trim=None, *args, **kwargs):
            _, _ = args, kwargs

            # propagation from child retries until succeed
            while True:
                parent, prv, pgn = util.get_spec(g, v, r, n, ns)

                # check if child exists
                mounts = parent.get("mount", {})
                gvr_str = util.gvr(group, version, plural)
                nsn_str = util.spaced_name(name, namespace)

                if (gvr_str not in mounts or
                        (nsn_str not in mounts[gvr_str] and
                         name not in mounts[gvr_str])):
                    print(f"unable to find the {nsn_str} or {name} in the {parent}")
                    return

                models = mounts[gvr_str]
                n_ = name if name in models else nsn_str

                if spec is None:
                    parent_patch = None  # will convert to json null
                else:
                    if models[n_].get("mode", "hide") == "hide":
                        if attrs_to_trim is None:
                            attrs_to_trim = set()
                        attrs_to_trim.add("mount")

                    parent_patch = _gen_parent_patch(spec, diff, attrs_to_trim)

                parent_patch = {
                    "mount": {
                        gvr_str: {
                            n_: None if parent_patch is None else {
                                "spec": parent_patch,
                                "version": meta["resourceVersion"],
                                "generation": meta["generation"],
                            }
                        }
                    }}

                # maybe rejected if parent has been updated;
                # continue to try until succeed
                e = util.patch_spec(g, v, r, n, ns, parent_patch, rv=prv)
                if e is not None:
                    print(f"mounter: failed to sync to parent due to {e}")
                    time.sleep(1)
                else:
                    self._parent_gen = pgn
                    break

        def _gen_parent_patch(child_spec, diff, attrs_to_trim=None):
            child_spec = dict(child_spec)

            if attrs_to_trim is not None:
                child_spec = util.trim_attr(child_spec, attrs_to_trim)

            if diff is not None:
                child_spec = util.apply_diff({"spec": child_spec}, diff)["spec"]

            return child_spec

        """ parent event handlers """

        def on_parent_create(spec, diff, *args, **kwargs):
            _, _ = args, kwargs
            _update_children_watches(spec)
            # no need to sync from the children as the child
            # handlers will sync updates from/to the parent
            # ...
            # _sync_to_children(spec, diff)

        def on_mount_attr_update(spec, meta, diff, *args, **kwargs):
            _, _ = args, kwargs

            if meta["generation"] == self._parent_gen + 1:
                return

            _update_children_watches(spec)
            _sync_to_children(spec, diff)

        def on_parent_delete(*args, **kwargs):
            _, _ = args, kwargs
            self.stop()

        def _update_children_watches(spec: dict):
            # iterate over mounts and add/trim child event watches
            mounts = spec.get("mount", {})

            # add watches
            for gvr_str, models in mounts.items():
                gvr = parse_gvr(gvr_str)  # child's gvr

                for nsn_str, m in models.items():
                    nsn = parse_spaced_name(nsn_str)
                    # in case default ns is omitted in the model
                    nsn_str = spaced_name(*nsn)

                    if gvr_str in self._children_watches and \
                            nsn_str in self._children_watches[gvr_str]:
                        continue

                    # TBD: add child event handlers
                    self._children_watches[gvr_str][nsn_str] \
                        = Watch(*gvr, *nsn,
                                create_fn=on_child_create,
                                resume_fn=on_child_create,
                                update_fn=on_child_update,
                                delete_fn=on_child_delete).start()

            # trim watches no longer needed
            for gvr_str, model_watches in self._children_watches.items():
                if gvr_str not in mounts:
                    for _, w in model_watches.items():
                        w.stop()
                    del self._children_watches[gvr_str]

                for nsn_str, w in model_watches.items():
                    models = mounts[gvr_str]
                    if nsn_str not in models and \
                            util.trim_default_space(nsn_str) not in models:
                        w.stop()
                        del model_watches[nsn_str]

        def _gen_child_patch(parent_spec, gvr_str, nsn_str):
            mount_entry = parent_spec \
                .get("mount", {}) \
                .get(gvr_str, {}) \
                .get(nsn_str, {})
            if mount_entry.get("mode", "hide") == "hide":
                mount_entry.get("spec", {}).pop("mount", {})

            if mount_entry.get("status", "inactive") == "active":
                spec = mount_entry.get("spec", None)
                if spec is not None:
                    spec = util.trim_attr(spec, {"status", "output", "obs"})

                version = mount_entry.get("version", None)
                gen = mount_entry.get("generation", None)
                return spec, version, gen

            return None, None, None

        def _sync_to_children(parent_spec, diff):
            # sort the diff by the attribute path (in tuple)
            diff = sorted(diff, key=lambda x: x[1])

            # filter to only the intent/input updates
            to_sync = dict()
            for _, f, _, _ in diff:
                # skip non children update
                if len(f) < 3:
                    continue

                gvr_str, nsn_str = f[0], f[1]
                model_id = util.model_id(*parse_gvr(gvr_str),
                                         *parse_spaced_name(nsn_str))

                if model_id not in to_sync:
                    cs, rv, gen = _gen_child_patch(parent_spec, gvr_str, nsn_str)
                    if not (cs is None or rv is None or gen is None):
                        to_sync[model_id] = cs, rv, gen

            # sync all, e.g., on parent resume and creation
            if len(diff) == 0:
                for gvr_str, ms in parent_spec.get("mount", {}).items():
                    for nsn_str, m in ms.items():
                        model_id = util.model_id(*parse_gvr(gvr_str),
                                                 *parse_spaced_name(nsn_str))
                        cs, rv, gen = _gen_child_patch(parent_spec, gvr_str, nsn_str)
                        # both rv and gen can be none as during the initial sync
                        # the parent may overwrite
                        if cs is not None:
                            to_sync[model_id] = cs, rv, gen

            # push to children models
            # TBD: transactional update
            for model_id, (cs, rv, gen) in to_sync.items():
                e = util.patch_spec(*util.parse_model_id(model_id),
                                    spec=cs,
                                    rv=rv)
                if e is not None:
                    print(f"mounter: unable to sync to children due to {e}")
                elif gen is not None:
                    self._children_gen[model_id] = gen

        # subscribe to the events of the parent model
        self._parent_watch = Watch(g, v, r, n, ns,
                                   create_fn=on_parent_create,
                                   resume_fn=on_parent_create,
                                   field_fn=on_mount_attr_update, field="spec.mount",
                                   delete_fn=on_parent_delete, delete_optional=True)

        # subscribe to the events of the child models;
        # keyed by the gvr and then spaced name
        self._children_watches = defaultdict(dict)

        # last handled generation of a child, keyed by nsn;
        # used to filter last self-write on the child
        self._children_gen = dict()
        self._parent_gen = -1

    def start(self):
        self._parent_watch.start()

    def stop(self):
        self._parent_watch.stop()
        for _, mws in self._children_watches.items():
            for _, w in mws.items():
                w.stop()
        return self


def test():
    gvr = ("mock.digi.dev", "v1", "samples")
    Mounter(*gvr, n="sample").start()


if __name__ == '__main__':
    test()
