from proto.MsgLstStorPool_pb2 import MsgLstStorPool
from proto.MsgCrtStorPool_pb2 import MsgCrtStorPool
from proto.MsgDelStorPool_pb2 import MsgDelStorPool
from proto.MsgModStorPool_pb2 import MsgModStorPool
from linstor.commcontroller import need_communication, completer_communication
from linstor.commands import Commands, NodeCommands
from linstor.utils import namecheck, Table
from linstor.sharedconsts import (
    API_CRT_STOR_POOL,
    API_MOD_STOR_POOL,
    API_DEL_STOR_POOL,
    API_LST_STOR_POOL,
    KEY_STOR_POOL_VOLUME_GROUP,
    KEY_STOR_POOL_THIN_POOL,
    KEY_STOR_POOL_ZPOOL,
    KEY_STOR_POOL_SUPPORTS_SNAPSHOTS,
    NAMESPC_STORAGE_DRIVER
)
from linstor.consts import NODE_NAME, STORPOOL_NAME


class StoragePoolCommands(Commands):
    device_key_map = {
        'Lvm': KEY_STOR_POOL_VOLUME_GROUP,
        'LvmThin': KEY_STOR_POOL_THIN_POOL,
        'Zfs': KEY_STOR_POOL_ZPOOL
    }

    @classmethod
    def get_driver_key(cls, driver_name):
        return NAMESPC_STORAGE_DRIVER + '/' + StoragePoolCommands.device_key_map[driver_name[:-len('Driver')]]

    @staticmethod
    def setup_commands(parser):
        # new-storpol
        p_new_storpool = parser.add_parser(
            Commands.CREATE_STORAGE_POOL,
            aliases=['crtstorpool'],
            description='Defines a Linstor storage pool for use with Linstor.')
        p_new_storpool.add_argument('name', type=namecheck(STORPOOL_NAME), help='Name of the new storage pool')
        p_new_storpool.add_argument(
            'node_name',
            type=namecheck(NODE_NAME),
            help='Name of the node for the new storage pool').completer = NodeCommands.completer
        p_new_storpool.add_argument(
            'driver',
            choices=StoragePoolCommands.driver_completer(""),
            help='Name of the driver used for the new storage pool').completer = StoragePoolCommands.driver_completer
        p_new_storpool.add_argument(
            'driver_pool_name',
            type=namecheck(STORPOOL_NAME),  # TODO use STORPOOL_NAME check for now
            help='Volumegroup/Pool name of the driver e.g. drbdpool')
        p_new_storpool.set_defaults(func=StoragePoolCommands.create)

        # remove-storpool
        # TODO description
        p_rm_storpool = parser.add_parser(
            Commands.DELETE_STORAGE_POOL,
            aliases=['delstorpool'],
            description=' Removes a storage pool ')
        p_rm_storpool.add_argument(
            '-q', '--quiet',
            action="store_true",
            help='Unless this option is used, linstor will issue a safety question '
            'that must be answered with yes, otherwise the operation is canceled.')
        p_rm_storpool.add_argument('name',
                                   help='Name of the storage pool to delete').completer = StoragePoolCommands.completer
        p_rm_storpool.add_argument(
            'node_name',
            nargs="+",
            help='Name of the Node where the storage pool exists.').completer = NodeCommands.completer
        p_rm_storpool.set_defaults(func=StoragePoolCommands.delete)

        # list storpool
        storpoolgroupby = ('Name')
        storpool_group_completer = Commands.show_group_completer(storpoolgroupby, "groupby")

        p_lstorpool = parser.add_parser(
            Commands.LIST_STORAGE_POOL,
            aliases=['list-storage-pool', 'ls-storage-pool', 'display-storage-pools', 'dspstorpool'],
            description='Prints a list of all storage pool known to '
            'linstor. By default, the list is printed as a human readable table.')
        p_lstorpool.add_argument('-p', '--pastable', action="store_true", help='Generate pastable output')
        p_lstorpool.add_argument('-g', '--groupby', nargs='+',
                                 choices=storpoolgroupby).completer = storpool_group_completer
        p_lstorpool.add_argument('-R', '--storpool', nargs='+', type=namecheck(STORPOOL_NAME),
                                 help='Filter by list of storage pool').completer = StoragePoolCommands.completer
        p_lstorpool.set_defaults(func=StoragePoolCommands.list)

        # show properties
        p_sp = parser.add_parser(
            Commands.GET_STORAGE_POOL_PROPS,
            aliases=['get-storage-pool-properties', 'dspstorpoolprp'],
            description="Prints all properties of the given storage pool.")
        p_sp.add_argument(
            'storage_pool_name',
            help="Storage pool for which to print the properties").completer = StoragePoolCommands.completer
        p_sp.add_argument(
            'node_name',
            type=namecheck(NODE_NAME),
            help='Name of the node for the storage pool').completer = NodeCommands.completer
        p_sp.set_defaults(func=StoragePoolCommands.print_props)

        # set properties
        p_setprop = parser.add_parser(
            Commands.SET_STORAGE_POOL_PROPS,
            aliases=['set-storage-pool-properties', 'setstorpoolprp'],
            description='Sets properties for the given storage pool on the given node.')
        p_setprop.add_argument('name', type=namecheck(STORPOOL_NAME), help='Name of the storage pool')
        p_setprop.add_argument(
            'node_name',
            type=namecheck(NODE_NAME),
            help='Name of the node for the storage pool').completer = NodeCommands.completer
        p_setprop.add_argument(
            'key_value_pair',
            nargs='+',
            help="Key value pair in the format 'key=value'."
        )
        p_setprop.set_defaults(func=StoragePoolCommands.set_props)

    @staticmethod
    @need_communication
    def create(cc, args):
        p = MsgCrtStorPool()
        p.stor_pool.stor_pool_name = args.name
        p.stor_pool.node_name = args.node_name

        # construct correct driver name
        if args.driver == 'lvmthin':
            driver = 'LvmThin'
        else:
            driver = args.driver.title()

        p.stor_pool.driver = '{driver}Driver'.format(driver=driver)

        # set driver device pool property
        prop = p.stor_pool.props.add()
        prop.key = StoragePoolCommands.get_driver_key(p.stor_pool.driver)
        prop.value = args.driver_pool_name

        return Commands._send_msg(cc, API_CRT_STOR_POOL, p, args)

    @staticmethod
    @need_communication
    def delete(cc, args):
        del_msgs = []
        for node_name in args.node_name:
            p = MsgDelStorPool()
            p.stor_pool_name = args.name
            p.node_name = node_name

            del_msgs.append(p)

        return Commands._delete_and_output(cc, args, API_DEL_STOR_POOL, del_msgs)

    @staticmethod
    @need_communication
    def list(cc, args):
        lstmsg = Commands._get_list_message(cc, API_LST_STOR_POOL, MsgLstStorPool(), args)

        if lstmsg:
            tbl = Table(utf8=not args.no_utf8, colors=not args.no_color, pastable=args.pastable)
            tbl.add_column("StoragePool")
            tbl.add_column("Node")
            tbl.add_column("Driver")
            tbl.add_column("PoolName")
            tbl.add_column("SupportsSnapshots")
            for storpool in lstmsg.stor_pools:
                driver_device_prop = [x for x in storpool.props
                                      if x.key == StoragePoolCommands.get_driver_key(storpool.driver)]
                driver_device = driver_device_prop[0].value if driver_device_prop else ''

                supports_snapshots_prop = [x for x in storpool.static_traits if x.key == KEY_STOR_POOL_SUPPORTS_SNAPSHOTS]
                supports_snapshots = supports_snapshots_prop[0].value if supports_snapshots_prop else ''

                tbl.add_row([
                    storpool.stor_pool_name,
                    storpool.node_name,
                    storpool.driver,
                    driver_device,
                    supports_snapshots
                ])
            tbl.show()

        return None

    @staticmethod
    @need_communication
    def print_props(cc, args):
        lstmsg = Commands._request_list(cc, API_LST_STOR_POOL, MsgLstStorPool())

        result = []
        if lstmsg:
            for stp in lstmsg.stor_pools:
                if stp.stor_pool_name == args.storage_pool_name and stp.node_name == args.node_name:
                    result.append(stp.props)
                    break

        Commands._print_props(result, args.machine_readable)
        return None

    @staticmethod
    @need_communication
    def set_props(cc, args):
        mmn = MsgModStorPool()
        mmn.node_name = args.node_name
        mmn.stor_pool_name = args.name

        Commands.fill_override_props(mmn, args.key_value_pair)

        return Commands._send_msg(cc, API_MOD_STOR_POOL, mmn, args)

    @staticmethod
    @completer_communication
    def completer(cc, prefix, **kwargs):
        possible = set()
        lstmsg = Commands._get_list_message(cc, API_LST_STOR_POOL, MsgLstStorPool())

        if lstmsg:
            for storpool in lstmsg.resources:
                possible.add(storpool.stor_pool_name)

            if prefix:
                return [res for res in possible if res.startswith(prefix)]

        return possible

    @staticmethod
    def driver_completer(prefix, **kwargs):
        possible = ["lvm", "lvmthin", "zfs"]

        if prefix:
            return [e for e in possible if e.startswith(prefix)]

        return possible
